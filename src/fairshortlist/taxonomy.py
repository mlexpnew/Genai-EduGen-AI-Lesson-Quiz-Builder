"""Skill taxonomy: canonical names and the many ways resumes write them.

"k8s", "Kubernetes" and "kubernetes" are one skill; "Java" is not "JavaScript".
Matching uses word boundaries so "R" or "Go" never match inside other words.
"""

from __future__ import annotations

import re

SKILLS: dict[str, list[str]] = {
    "python": ["python", "python3"],
    "sql": ["sql", "t-sql", "pl/sql"],
    "postgresql": ["postgresql", "postgres"],
    "mongodb": ["mongodb", "mongo"],
    "java": ["java"],
    "javascript": ["javascript", "js", "node.js", "nodejs"],
    "typescript": ["typescript"],
    "react": ["react", "react.js", "reactjs"],
    "go": ["golang"],
    "fastapi": ["fastapi"],
    "flask": ["flask"],
    "django": ["django"],
    "rest api": ["rest api", "rest apis", "restful", "rest services"],
    "docker": ["docker", "containerization", "containerised", "containerized"],
    "kubernetes": ["kubernetes", "k8s", "eks", "aks", "gke"],
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda", "sagemaker"],
    "gcp": ["gcp", "google cloud", "bigquery", "vertex ai"],
    "azure": ["azure"],
    "terraform": ["terraform"],
    "ci/cd": ["ci/cd", "github actions", "jenkins", "gitlab ci"],
    "git": ["git", "github", "gitlab"],
    "linux": ["linux", "bash", "shell scripting"],
    "spark": ["spark", "pyspark", "databricks"],
    "airflow": ["airflow"],
    "kafka": ["kafka"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "keras"],
    "machine learning": ["machine learning", "ml models", "predictive modelling",
                         "predictive modeling"],  # fmt: skip
    "deep learning": ["deep learning", "neural networks"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision", "opencv", "image classification"],
    "llm": ["llm", "llms", "large language models", "gpt", "gemini", "llama", "claude"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "langchain": ["langchain"],
    "langgraph": ["langgraph"],
    "crewai": ["crewai"],
    "agents": ["ai agents", "agentic", "multi-agent", "autonomous agents"],
    "vector database": ["vector database", "vector db", "faiss", "chromadb", "chroma",
                        "pinecone", "weaviate", "qdrant", "pgvector"],  # fmt: skip
    "prompt engineering": ["prompt engineering"],
    "hugging face": ["hugging face", "huggingface", "transformers"],
    "mlops": ["mlops", "mlflow", "model monitoring", "model deployment"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "excel": ["excel", "advanced excel", "vlookup", "pivot tables"],
    "statistics": ["statistics", "statistical analysis", "a/b testing", "hypothesis testing"],
    "streamlit": ["streamlit"],
    "redis": ["redis"],
    "pytest": ["pytest", "unit testing", "test automation"],
    "data visualization": ["data visualization", "data visualisation", "dashboards",
                           "matplotlib", "plotly", "seaborn"],  # fmt: skip
}

_PATTERNS = {
    canon: re.compile(
        r"(?<![\w.+#/-])(?:" + "|".join(re.escape(a) for a in sorted(set(aliases + [canon]),
                                                                    key=len, reverse=True))
        + r")(?![\w+#-])",
        re.I,
    )
    for canon, aliases in SKILLS.items()
}  # fmt: skip


# Using a framework proves the broader skill: FastAPI work is REST API work.
IMPLIES: dict[str, list[str]] = {
    "fastapi": ["rest api", "python"],
    "flask": ["rest api", "python"],
    "django": ["rest api", "python"],
    "langgraph": ["agents"],
    "crewai": ["agents"],
    "pandas": ["python"],
}


def _expand(skills: set[str]) -> set[str]:
    out = set(skills)
    for s in skills:
        out.update(IMPLIES.get(s, []))
    return out


def find(text: str) -> set[str]:
    return _expand({canon for canon, pat in _PATTERNS.items() if pat.search(text)})


def find_in_lines(lines: list[str]) -> dict[str, list[str]]:
    """Skill -> lines it appears in (the evidence a recruiter can read)."""
    out: dict[str, list[str]] = {}
    for line in lines:
        for canon, pat in _PATTERNS.items():
            if pat.search(line):
                for skill in _expand({canon}):
                    out.setdefault(skill, []).append(line.strip())
    return out
