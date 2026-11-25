from pathlib import Path
import tempfile
import shutil

import pytest


@pytest.fixture(scope="function")
def temp_path() -> Path:
    tmp_dir = Path(tempfile.mkdtemp())
    yield tmp_dir
    shutil.rmtree(tmp_dir)


@pytest.fixture(scope="session")
def data_path() -> Path:
    return Path(Path(__file__).parent, 'data')
