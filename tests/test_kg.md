Usage                                                                        
  # Test Neo4j connection                                                   
  python -m tests.test_kg test-conn

  # Import knowledge graph from output_history
  python -m tests.test_kg import --kg-type diet   # diet only
  python -m tests.test_kg import --kg-type all    # diet + exercise

  # Show database statistics
  python -m tests.test_kg stats

  # Run custom Cypher query
  python -m tests.test_kg query "MATCH (n:Food) RETURN n.name LIMIT 5"      

  # Search for entities
  python -m tests.test_kg search diabetes

  # Show sample data
  python -m tests.test_kg sample

  # Run complete demo
  python -m tests.test_kg demo

  # Clear all data (with confirmation)
  python -m tests.test_kg clear

  # Show help
  python -m tests.test_kg --help