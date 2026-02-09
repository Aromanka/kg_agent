"""
CLI Tests and Debug Tools for Neo4j Knowledge Graph
Run with: python -m tests.test_kg [command] [options]

Commands:
  test-conn     - Test Neo4j connection
  import         - Import KG from output_history
  stats          - Show database statistics
  query <cypher> - Run custom Cypher query
  search <word>  - Search for entities
  sample         - Show sample entities and relationships
  clear          - Clear all data (requires confirmation)
  demo           - Run complete demo workflow
"""
import os
import sys
import json
import glob
import click
from datetime import datetime
from neo4j import GraphDatabase
from config_loader import NEO4J_URI, NEO4J_AUTH

# ================= Neo4j Connection =================
driver = None

def get_driver():
    """Get Neo4j driver"""
    global driver
    if driver is None:
        driver = GraphDatabase.driver(NEO4J_URI(), auth=NEO4J_AUTH())
    return driver

def close_driver():
    """Close Neo4j driver"""
    global driver
    if driver:
        driver.close()
        driver = None

# ================= Utility Functions =================

def run_query(tx, query, params=None):
    """Execute a query and return results"""
    result = tx.run(query, params or {})
    return [record.data() for record in result]

def print_result(title, result, max_items=10):
    """Print query result in a formatted way"""
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")
    if not result:
        print("  (no results)")
        return
    count = 0
    for record in result:
        if count >= max_items:
            print(f"  ... and {len(result) - max_items} more")
            break
        print(f"  {json.dumps(record, ensure_ascii=False, indent=2)}")
        count += 1
    print(f"\n  Total: {len(result)} records")

# ================= CLI Commands =================

@click.group()
def cli():
    """Neo4j Knowledge Graph CLI Tools"""
    pass

@click.command()
def test_conn():
    """Test Neo4j database connection"""
    click.echo("\n[TEST] Testing Neo4j connection...")
    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run("RETURN 'Neo4j Connected!' as message, datetime() as timestamp")
            record = result.single()
            click.secho(f"  ✓ Connected successfully!", fg="green")
            click.echo(f"  ✓ Server time: {record['timestamp']}")
    except Exception as e:
        click.secho(f"  ✗ Connection failed: {e}", fg="red")
        sys.exit(1)

@click.command()
@click.option('--kg-type', type=click.Choice(['diet', 'exercise', 'all']), default='all',
              help='KG type to import')
def import_kg(kg_type):
    """Import knowledge graph from output_history"""
    from core.import_kg import (
        import_from_output_history, create_indexes, show_stats
    )

    click.echo(f"\n[IMPORT] Importing {kg_type} knowledge graph...")

    try:
        with get_driver().session() as session:
            create_indexes(session)

            if kg_type == 'all':
                total = import_from_output_history(session)
            else:
                pattern = f"output_history/*{kg_type.capitalize()}*/*.{kg_type}_triplets.*"
                files = glob.glob(pattern)
                total = 0
                for f in files:
                    if f.endswith('.json'):
                        from core.import_kg import import_json_triplets
                        total += import_json_triplets(session, f)
                    elif f.endswith('.csv'):
                        from core.import_kg import import_csv_triplets
                        total += import_csv_triplets(session, f)

            click.secho(f"  ✓ Imported {total} relationships", fg="green")
            show_stats(session)
    except Exception as e:
        click.secho(f"  ✗ Import failed: {e}", fg="red")
        sys.exit(1)

@click.command()
def stats():
    """Show database statistics"""
    from core.import_kg import show_stats
    try:
        with get_driver().session() as session:
            show_stats(session)
    except Exception as e:
        click.secho(f"  ✗ Failed: {e}", fg="red")
        sys.exit(1)

@click.command()
@click.argument('cypher')
def query(cypher):
    """Run custom Cypher query"""
    click.echo(f"\n[QUERY] Executing: {cypher[:60]}...")
    try:
        with get_driver().session() as session:
            result = session.run(cypher)
            records = [r.data() for r in result]
            print_result("Query Results", records, max_items=20)
    except Exception as e:
        click.secho(f"  ✗ Query failed: {e}", fg="red")
        sys.exit(1)

@click.command()
@click.argument('keyword')
@click.option('--threshold', type=float, default=0.1,
              help='Minimum score threshold for fulltext search')
def search(keyword, threshold):
    """Search for entities by keyword"""
    click.echo(f"\n[SEARCH] Searching for: {keyword}")
    try:
        with get_driver().session() as session:
            # Try fulltext search first
            fulltext_query = """
            CALL db.index.fulltext.queryNodes("search_index", $word) YIELD node, score
            WHERE score > $threshold
            MATCH (node)-[r]-(m)
            RETURN node.name as head, type(r) as rel_type, m.name as tail, score
            ORDER BY score DESC
            LIMIT 20
            """
            fulltext_result = session.run(fulltext_query, word=keyword, threshold=threshold)
            ft_rels = [r.data() for r in fulltext_result]
            if ft_rels:
                click.secho(f"\n[Fulltext Search Results for '{keyword}']:", fg="cyan", bold=True)
                for r in ft_rels:
                    click.echo(f"  {r['head']} -[{r['rel_type']}]-> {r['tail']} (score: {r['score']:.3f})")
            else:
                click.echo(f"\n[Fulltext Search] No results with threshold {threshold}")

            # Fallback to CONTAINS search
            query = """
            MATCH (n)
            WHERE toLower(n.name) CONTAINS toLower($keyword)
            RETURN n.name as name, labels(n) as labels
            ORDER BY n.name
            LIMIT 20
            """
            result = session.run(query, keyword=keyword)
            entities = [r.data() for r in result]
            print_result(f"Entities matching '{keyword}' (CONTAINS)", entities)

            # Also search relationships
            rel_query = """
            MATCH ()-[r]->()
            WHERE toLower(type(r)) CONTAINS toLower($keyword)
            RETURN type(r) as type, count(r) as count
            ORDER BY count DESC
            """
            rel_result = session.run(rel_query, keyword=keyword)
            rels = [r.data() for r in rel_result]
            print_result(f"Relationship types matching '{keyword}'", rels)
    except Exception as e:
        click.secho(f"  ✗ Search failed: {e}", fg="red")
        sys.exit(1)

@click.command()
def sample():
    """Show sample entities and relationships"""
    click.echo("\n[SAMPLE] Showing sample data from database...")
    try:
        with get_driver().session() as session:
            # Sample entities
            print_result("Sample Entities (10)",
                run_query(session, "MATCH (n) RETURN n.name as name, labels(n) as labels LIMIT 10"))

            # Sample relationships
            print_result("Sample Relationships (10)",
                run_query(session, """
                    MATCH (h)-[r]->(t)
                    RETURN h.name as head, type(r) as relation, t.name as tail
                    LIMIT 10
                """))

            # Entity type distribution
            print_result("Entity Type Distribution",
                run_query(session, """
                    MATCH (n)
                    RETURN labels(n) as labels, count(n) as count
                    ORDER BY count DESC
                """))
    except Exception as e:
        click.secho(f"  ✗ Failed: {e}", fg="red")
        sys.exit(1)

@click.command()
def clear():
    """Clear all data from database"""
    click.secho("\n[WARN] This will delete ALL data from the database!", fg="red")
    if not click.confirm("Are you sure?"):
        click.echo("Cancelled.")
        return

    try:
        with get_driver().session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            click.secho("  ✓ Database cleared successfully!", fg="green")
    except Exception as e:
        click.secho(f"  ✗ Clear failed: {e}", fg="red")
        sys.exit(1)

@click.command()
def demo():
    """Run complete demo workflow"""
    click.secho("\n[Demo] Complete KG Demo Workflow", fg="cyan", bold=True)

    try:
        with get_driver().session() as session:
            # 1. Check connection
            click.echo("\n1. Testing connection...")
            result = session.run("RETURN 'OK' as status")
            click.secho(f"   ✓ {result.single()['status']}", fg="green")

            # 2. Count entities
            click.echo("\n2. Database overview:")
            ent_count = session.run("MATCH (n) RETURN count(n) as count").single()['count']
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()['count']
            click.echo(f"   - Entities: {ent_count}")
            click.echo(f"   - Relationships: {rel_count}")

            # 3. Discover actual labels in DB
            click.echo("\n3. Discovering schema...")
            label_result = session.run("""
                MATCH (n)
                RETURN labels(n) as labels, count(n) as count
                ORDER BY count DESC
            """)
            labels = [r.data() for r in label_result]
            click.echo("   Entity labels in database:")
            for r in labels[:10]:
                click.echo(f"     {r['labels']}: {r['count']}")

            # 4. Sample entities (generic)
            click.echo("\n4. Sample entities:")
            result = session.run("""
                MATCH (n)
                RETURN n.name as name, labels(n) as labels
                LIMIT 8
            """)
            for r in result:
                click.echo(f"   - {r['name']} ({r['labels']})")

            # 5. Sample relationships (generic)
            click.echo("\n5. Sample relationships:")
            result = session.run("""
                MATCH (h)-[r]->(t)
                RETURN h.name as head, type(r) as rel, t.name as tail
                LIMIT 8
            """)
            for r in result:
                click.echo(f"   - {r['head']} -[{r['rel']}]-> {r['tail']}")

            # 6. Search for entities containing 'diabetes' or similar
            click.echo("\n6. Searching for diabetes-related entities:")
            result = session.run("""
                MATCH (n)
                WHERE toLower(n.name) CONTAINS 'diabetes' OR toLower(n.name) CONTAINS 'blood sugar'
                RETURN n.name as name, labels(n) as labels
                LIMIT 5
            """)
            found = False
            for r in result:
                click.echo(f"   - {r['name']} ({r['labels']})")
                found = True
            if not found:
                click.echo("   (none found with exact match)")

            # 7. Search for food-related entities
            click.echo("\n7. Searching for food-related entities:")
            result = session.run("""
                MATCH (n)
                WHERE toLower(n.name) CONTAINS 'apple' OR toLower(n.name) CONTAINS 'rice'
                       OR toLower(n.name) CONTAINS 'vegetable' OR toLower(n.name) CONTAINS 'chicken'
                RETURN n.name as name, labels(n) as labels
                LIMIT 5
            """)
            found = False
            for r in result:
                click.echo(f"   - {r['name']} ({r['labels']})")
                found = True
            if not found:
                click.echo("   (none found with exact match)")

            click.secho("\n   ✓ Demo completed!", fg="green")

    except Exception as e:
        click.secho(f"  ✗ Demo failed: {e}", fg="red")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# ================= Register Commands =================
cli.add_command(test_conn, 'test-conn')
cli.add_command(import_kg, 'import')
cli.add_command(stats, 'stats')
cli.add_command(query, 'query')
cli.add_command(search, 'search')
cli.add_command(sample, 'sample')
cli.add_command(clear, 'clear')
cli.add_command(demo, 'demo')

# ================= Main =================
if __name__ == "__main__":
    try:
        cli()
    finally:
        close_driver()
