from typing import List, Dict
from neo4j import GraphDatabase
from deep_translator import GoogleTranslator
import numpy as np
import time
import warnings

warnings.filterwarnings("ignore")

# ==========================================
# 1. Neo4j 연동 모듈 (Knowledge Graph)
# ==========================================
class KGSearcher:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password123", enable_db=True):
        self.enable_db = enable_db
        if self.enable_db:
            try:
                self.driver = GraphDatabase.driver(uri, auth=(user, password))
                self.driver.verify_connectivity()
                self.translator = GoogleTranslator(source='ko', target='en')
                self.translation_cache = {} # 번역 결과 캐싱 (속도 향상)
                print("Connected to Neo4j Database & Translator Ready (Optimized).")
            except Exception as e:
                print(f"Neo4j Connection Failed: {e}")
                print("Falling back to Dummy Data mode.")
                self.enable_db = False

    def close(self):
        if self.enable_db and hasattr(self, 'driver'):
            self.driver.close()

    def search_context(self, keywords_ko: List[str]) -> List[str]:
        contexts = []
        if not keywords_ko:
            return contexts

        if self.enable_db:
            # 실시간 번역: 한국어 키워드 -> 영어 키워드 변환 (캐시 및 배치 최적화)
            try:
                # 1. 캐시에 없는 단어들만 골라내기
                to_translate = [kw for kw in keywords_ko if kw not in self.translation_cache]
                
                if to_translate:
                    # 2. 여러 단어를 한 번에 번역 (네트워크 호출 1회로 단축)
                    results = self.translator.translate_batch(to_translate)
                    for ko, en in zip(to_translate, results):
                        self.translation_cache[ko] = en.lower()
                
                # 3. 전체 번역 결과 조립
                translated = [self.translation_cache[kw] for kw in keywords_ko]
                
                # 검색 후보에 한국어와 번역된 영어를 모두 포함
                search_keywords = list(set(keywords_ko + translated))
            except Exception as e:
                print(f"Translation Error during KG Search: {e}")
                search_keywords = keywords_ko

            try:
                # 정규표현식은 100만 개 노드에서 너무 느리므로(18초 이상),
                # 단어 경계 매칭을 빠른 문자열 함수로 대체합니다.
                query = """
                MATCH (n:Concept)-[r:ATOMIC_REL]->(m:Concept)
                WHERE any(kw IN $keywords WHERE 
                    toLower(n.name) CONTAINS (' ' + kw + ' ') OR 
                    toLower(n.name) STARTS WITH (kw + ' ') OR 
                    toLower(n.name) ENDS WITH (' ' + kw) OR 
                    toLower(n.name) = kw
                )
                RETURN n.name AS source, r.type AS relation, m.name AS target
                LIMIT 5
                """
                
                with self.driver.session() as session:
                    result = session.run(query, keywords=search_keywords)
                    for record in result:
                        contexts.append(f"{record['source']}(은)는 {record['target']}(와)과 {record['relation']} 관계임")
            except Exception as e:
                print(f"Neo4j Query Error: {e}")

        return contexts

# ==========================================
# 2. 텍스트 키워드 추출 (Entity Linking)
# ==========================================
class TextProcessor:
    def __init__(self, enable_mecab=True):
        self.enable_mecab = enable_mecab
        if self.enable_mecab:
            try:
                from konlpy.tag import Mecab
                # Jetson/Ubuntu 설치 경로를 명시적으로 지정합니다.
                self.tagger = Mecab('/usr/lib/aarch64-linux-gnu/mecab/dic/mecab-ko-dic')
                print("Loading Mecab (C++) with mecab-ko-dic...")
            except Exception as e:
                print(f"Mecab 로드 실패 (설치 확인 필요): {e}")
                self.enable_mecab = False

    def extract_keywords(self, text: str) -> List[str]:
        if not self.enable_mecab:
            return []
            
        nouns = self.tagger.nouns(text)
        keywords = [noun for noun in nouns if len(noun) >= 2]
        return list(set(keywords))

# ==========================================
# 3. 텍스트 감성 분석 (On-Device 최적화)
# ==========================================
class TextSentimentAnalyzer:
    def __init__(self, enable=False):
        self.enable = enable
        if self.enable:
            try:
                from transformers import pipeline
                import torch
                print("Loading lightweight sentiment model for Jetson...")
                self.pipe = pipeline(
                    "text-classification", 
                    model="matthewburke/korean_sentiment", 
                    device=0 if torch.cuda.is_available() else -1
                )
            except Exception as e:
                print(f"transformers 모델 로드 실패 (에러: {e})\nDummy 모드로 작동합니다.")
                self.enable = False

    def get_sentiment(self, text: str) -> np.ndarray:
        """
        텍스트를 분석하여 Russell의 2차원 (Valence, Arousal) 벡터로 매핑합니다.
        """
        if not self.enable:
            # 모델이 꺼져있을 경우 중립 수치 반환 (가짜 우울증 삽입 금지)
            return np.array([0.0, 0.0], dtype=np.float32)
        
        result = self.pipe(text)[0]
        label = result['label']
        score = result['score']
        
        if label == "LABEL_1" or "pos" in label.lower(): 
            valence = score * 1.0
            arousal = 0.0
        else:
            valence = -score * 1.0
            arousal = score * 0.5
            
        return np.array([valence, arousal], dtype=np.float32)

# ==========================================
# 4. 정렬도 검사 (Sentiment Alignment Check)
# ==========================================
class AlignmentChecker:
    def __init__(self, threshold=0.5):
        self.threshold = threshold

    def check_alignment(self, text_sentiment_prob: np.ndarray, face_emotion_prob: np.ndarray) -> Dict:
        """
        언어(텍스트)의 감정과 비언어(표정/목소리)의 감정이 일치하는지 코사인 유사도로 검사합니다.
        """
        dot_product = np.dot(text_sentiment_prob, face_emotion_prob)
        norm_text = np.linalg.norm(text_sentiment_prob)
        norm_face = np.linalg.norm(face_emotion_prob)
        
        if norm_text == 0 or norm_face == 0:
            score = 0.0
        else:
            score = dot_product / (norm_text * norm_face)
            
        is_consistent = bool(score >= self.threshold)
        
        return {
            "score": round(float(score), 4),
            "is_consistent": is_consistent,
            "detected_anomaly": "Sarcasm/Suppression" if not is_consistent else "None"
        }

# ==========================================
# 5. Node C 메인 파이프라인 (팀 구조에 맞춰 PyTorch Fusion 제거)
# ==========================================
class NodeC:
    def __init__(self):
        self.kg_searcher = KGSearcher(enable_db=True)
        self.text_processor = TextProcessor(enable_mecab=True)
        self.sentiment_analyzer = TextSentimentAnalyzer(enable=True)
        self.alignment_checker = AlignmentChecker(threshold=0.5)

    def process_data(self, text: str, nonverbal_vector: np.ndarray) -> Dict:
        start_time = time.time()
        
        # 텍스트가 없는 경우 (표정 데이터만 들어온 경우 등) 무거운 분석 프로세스 스킵
        if not text or text.strip() == "":
            return {
                "kg_context": [],
                "alignment": {"score": 1.0, "is_consistent": True, "detected_anomaly": "None"},
                "priority": 1,
                "latency_ms": 0.0
            }

        # 1. Entity Linking & KG Search
        print(f"    [Step 1] 키워드 추출 및 KG 검색 중...", end=" ", flush=True)
        keywords = self.text_processor.extract_keywords(text)
        kg_context = self.kg_searcher.search_context(keywords)
        print(f"완료 ({len(kg_context)}건)")
        
        # 2. 텍스트 감성 추출 (V-A 모델)
        print(f"    [Step 2] 텍스트 감정 분석 중...", end=" ", flush=True)
        text_sentiment = self.sentiment_analyzer.get_sentiment(text)
        print(f"완료 (V:{text_sentiment[0]:.2f}, A:{text_sentiment[1]:.2f})")
        
        # 3. Sentiment Alignment Check
        alignment_result = self.alignment_checker.check_alignment(text_sentiment, nonverbal_vector)
        
        latency_ms = (time.time() - start_time) * 1000
        
        # PyTorch Fused Embedding 없이 순수 맥락(Context)만 반환
        payload = {
            "kg_context": kg_context,
            "alignment": alignment_result,
            "priority": 2 if not alignment_result["is_consistent"] else 1,
            "latency_ms": round(latency_ms, 2)
        }
        return payload
