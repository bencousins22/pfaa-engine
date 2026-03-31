"""VectorStore and TFIDFVectorizer test suite (from agents/team/spawn.py)."""
import math
import os
import sys
import tempfile
import shutil
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agents.team.spawn import TFIDFVectorizer, VectorStore, _tokenize, _cosine


# ── Tokenizer tests ──────────────────────────────────────────────────

class TestTokenize:
    def test_basic_tokenization(self):
        tokens = _tokenize("Hello World Python")
        assert "hello" in tokens
        assert "world" in tokens
        assert "python" in tokens

    def test_stop_words_removed(self):
        tokens = _tokenize("the quick brown fox is a very fast animal")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "a" not in tokens
        assert "very" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens

    def test_single_char_tokens_removed(self):
        tokens = _tokenize("I am a b c developer")
        # Single-char tokens should be excluded (len > 1 filter)
        for t in tokens:
            assert len(t) > 1

    def test_lowercased(self):
        tokens = _tokenize("PYTHON JavaScript TypeScript")
        assert all(t == t.lower() for t in tokens)

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_only_stop_words(self):
        assert _tokenize("the is a an to of in for on with") == []

    def test_special_characters_stripped(self):
        tokens = _tokenize("hello-world foo.bar baz_qux")
        # Regex [a-z0-9_]+ matches alphanumeric + underscore
        assert "hello" in tokens
        assert "world" in tokens
        assert "baz_qux" in tokens

    def test_numbers_preserved(self):
        tokens = _tokenize("python3 version 42")
        assert "python3" in tokens
        assert "42" in tokens


# ── Cosine similarity tests ──────────────────────────────────────────

class TestCosine:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine(a, b)) < 1e-9

    def test_empty_vectors(self):
        assert _cosine([], []) == 0.0
        assert _cosine([1.0], []) == 0.0
        assert _cosine([], [1.0]) == 0.0

    def test_different_lengths(self):
        # _cosine uses min(len(a), len(b))
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0]
        result = _cosine(a, b)
        assert isinstance(result, float)

    def test_zero_vector(self):
        assert _cosine([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_negative_values(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine(a, b) - (-1.0)) < 1e-9


# ── TFIDFVectorizer tests ───────────────────────────────────────────

class TestTFIDFVectorizer:
    def test_fit_transform_returns_list(self):
        v = TFIDFVectorizer()
        result = v.fit_transform(["hello", "world"])
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    def test_vocab_grows_with_new_tokens(self):
        v = TFIDFVectorizer()
        v.fit_transform(["hello", "world"])
        assert len(v._vocab) == 2
        v.fit_transform(["hello", "python"])
        assert len(v._vocab) == 3  # "hello", "world", "python"

    def test_doc_count_increments(self):
        v = TFIDFVectorizer()
        assert v.doc_count == 0
        v.fit_transform(["hello"])
        assert v.doc_count == 1
        v.fit_transform(["world"])
        assert v.doc_count == 2

    def test_doc_freqs_tracked(self):
        v = TFIDFVectorizer()
        v.fit_transform(["python", "code"])
        v.fit_transform(["python", "dev"])
        # "python" appears in 2 docs, "code" in 1, "dev" in 1
        assert v.doc_freqs["python"] == 2
        assert v.doc_freqs["code"] == 1
        assert v.doc_freqs["dev"] == 1

    def test_duplicate_tokens_counted_once_for_df(self):
        v = TFIDFVectorizer()
        v.fit_transform(["python", "python", "python"])
        assert v.doc_freqs["python"] == 1  # only 1 doc

    def test_empty_tokens(self):
        v = TFIDFVectorizer()
        result = v.fit_transform([])
        assert result == []

    def test_transform_empty_vocab(self):
        v = TFIDFVectorizer()
        result = v._transform(["hello"])
        assert result == []

    def test_vector_length_matches_vocab(self):
        v = TFIDFVectorizer()
        v.fit_transform(["alpha", "beta", "gamma"])
        vec = v._transform(["alpha"])
        assert len(vec) == 3

    def test_tfidf_values_positive(self):
        v = TFIDFVectorizer()
        vec = v.fit_transform(["python", "machine", "learning"])
        for val in vec:
            assert val >= 0.0

    def test_idf_reduces_common_terms(self):
        v = TFIDFVectorizer()
        # "common" in both docs, "rare" only in first
        v.fit_transform(["common", "rare"])
        v.fit_transform(["common", "other"])
        vec = v._transform(["common", "rare"])
        common_idx = v._vocab["common"]
        rare_idx = v._vocab["rare"]
        # "rare" should have higher IDF weight since it appears in fewer docs
        assert vec[rare_idx] > vec[common_idx]


# ── VectorStore tests ────────────────────────────────────────────────

@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestVectorStore:
    def test_upsert_and_get(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        store.upsert("doc1", "python programming language", {"q_value": 0.8})
        doc = store.get("doc1")
        assert doc is not None
        assert doc["id"] == "doc1"
        assert doc["text"] == "python programming language"
        assert doc["metadata"]["q_value"] == 0.8
        store.close()

    def test_get_nonexistent(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        assert store.get("nope") is None
        store.close()

    def test_upsert_overwrites(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        store.upsert("doc1", "original text", {"v": 1})
        store.upsert("doc1", "updated text", {"v": 2})
        doc = store.get("doc1")
        assert doc["text"] == "updated text"
        assert doc["metadata"]["v"] == 2
        assert store.count() == 1
        store.close()

    def test_count(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        assert store.count() == 0
        store.upsert("a", "alpha", {})
        assert store.count() == 1
        store.upsert("b", "beta", {})
        assert store.count() == 2
        store.close()

    def test_search_returns_results(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        store.upsert("d1", "python machine learning tensorflow", {"q_value": 0.8})
        store.upsert("d2", "javascript react web frontend", {"q_value": 0.5})
        store.upsert("d3", "python data science pandas numpy", {"q_value": 0.7})
        results = store.search("python machine learning")
        assert len(results) >= 1
        # Results are (doc_id, score, metadata) tuples
        ids = [r[0] for r in results]
        assert "d1" in ids  # best match

        # Scores should be sorted descending
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)
        store.close()

    def test_search_top_k(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        for i in range(10):
            store.upsert(f"doc{i}", f"document number {i} about testing", {})
        results = store.search("testing", top_k=3)
        assert len(results) <= 3
        store.close()

    def test_search_empty_query(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        store.upsert("d1", "hello world", {})
        results = store.search("")
        assert results == []
        store.close()

    def test_search_stop_words_only(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        store.upsert("d1", "hello world", {})
        results = store.search("the is a")
        assert results == []
        store.close()

    def test_metadata_default_none(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        store.upsert("d1", "test doc")
        doc = store.get("d1")
        assert doc["metadata"] == {}
        store.close()

    def test_q_value_affects_ranking(self, tmp_dir):
        store = VectorStore(os.path.join(tmp_dir, "vs.db"))
        # Same text but different q_values
        store.upsert("low_q", "python programming", {"q_value": 0.1})
        store.upsert("high_q", "python programming", {"q_value": 0.99})
        results = store.search("python programming")
        # high_q should rank higher due to q_value weighting
        assert results[0][0] == "high_q"
        store.close()

    def test_close_and_reopen(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "vs.db")
        store = VectorStore(db_path)
        store.upsert("d1", "persistent data", {"key": "value"})
        store.close()
        # Reopen — data should persist
        store2 = VectorStore(db_path)
        assert store2.count() == 1
        doc = store2.get("d1")
        assert doc is not None
        assert doc["text"] == "persistent data"
        store2.close()
