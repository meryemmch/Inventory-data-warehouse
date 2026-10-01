import pytest

from src import pipeline
from src.db import get_engine


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory):
    """Run the whole pipeline once into a temporary SQLite file and share the engine."""
    db_path = tmp_path_factory.mktemp("dwh") / "test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    counts = pipeline.run(database_url=url, processed_dir=None, seed=42)
    engine = get_engine(url)
    yield engine, counts
    engine.dispose()
