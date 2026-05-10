from neo4j import GraphDatabase

class KnowledgeRepository:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def get_emotional_context(self, keyword):
        with self.driver.session() as session:
            # VAD 수치와 관계를 기반으로 상위 5개 지식 추출
            query = """
            MATCH (n:Concept {name: $name})-[r:EMOTIONAL_REL]->(m)
            RETURN n.name as head, r.type as rel, m.name as tail, r.valence as v
            ORDER BY r.weight DESC LIMIT 5
            """
            result = session.run(query, name=keyword.lower())
            return [f"{record['head']} {record['rel']} {record['tail']} (Valence: {record['v']})" for record in result]
