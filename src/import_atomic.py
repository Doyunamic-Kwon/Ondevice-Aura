import csv
from neo4j import GraphDatabase
import time
import warnings

warnings.filterwarnings("ignore")

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "password123"

def clear_db(session):
    print("🧨 기존 노이즈 데이터 삭제 중... (잠시만 기다려주세요)")
    try:
        # 최신 Neo4j 버전의 트랜잭션 분할 삭제 방식
        session.run("MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS")
    except:
        # 구버전 대비용
        session.run("MATCH (n) DETACH DELETE n")
    print("✅ 기존 데이터 삭제 완료!")

def create_indexes(session):
    print("🛠 검색 속도 향상을 위해 인덱스 생성 중...")
    try:
        session.run("CREATE INDEX node_name IF NOT EXISTS FOR (n:Concept) ON (n.name)")
    except Exception as e:
        pass

def import_data(driver, tsv_path):
    print(f"🚀 ATOMIC 데이터셋 고속 로드 시작: {tsv_path}")
    
    batch = []
    batch_size = 5000
    total_count = 0
    
    # 동적 엣지 생성을 위해 APOC 없이 속성(type)으로 관계 이름을 저장합니다.
    safe_query = """
    UNWIND $batch AS row
    MERGE (head:Concept {name: row.head})
    MERGE (tail:Concept {name: row.tail})
    MERGE (head)-[:ATOMIC_REL {type: row.relation}]->(tail)
    """
    
    start_time = time.time()
    
    with open(tsv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if len(row) < 3:
                continue
            head, relation, tail = row[0], row[1], row[2]
            
            # 의미 없는 'none' 응답은 공감에 방해되므로 제외
            if tail.strip().lower() == "none":
                continue
                
            batch.append({
                "head": head.lower(),
                "relation": relation,
                "tail": tail.lower()
            })
            
            if len(batch) >= batch_size:
                with driver.session() as session:
                    session.run(safe_query, batch=batch)
                total_count += len(batch)
                batch = []
                elapsed = time.time() - start_time
                if total_count % 50000 == 0:
                    print(f"  ... {total_count}개 엣지 저장 완료 ({elapsed:.1f}초 경과)")
                
        # 남은 배치 처리
        if batch:
            with driver.session() as session:
                session.run(safe_query, batch=batch)
            total_count += len(batch)
            
    print(f"🎉 총 {total_count}개의 고품질 공감 지식이 DB에 저장되었습니다! (소요 시간: {time.time() - start_time:.1f}초)")

if __name__ == "__main__":
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        clear_db(session)
        create_indexes(session)
    import_data(driver, "/home/ys9072/EmpathyModel/train.tsv")
    driver.close()
