import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import pytest


@pytest.fixture(autouse=True)
def _fresh_streamlit_caches():
    """app.py caches the LLM client with st.cache_resource; don't leak it between tests."""
    import streamlit as st

    st.cache_resource.clear()
    yield
