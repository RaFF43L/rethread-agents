import pytest

from ai.utils import chunk_to_text, cited_skus, sanitize_customer_message


class TestSanitizeCustomerMessage:
    def test_plain_message_is_kept(self):
        text = "Oi! Essa calça veste bem um 40."
        assert sanitize_customer_message(text) == text

    def test_empty(self):
        assert sanitize_customer_message("") == ""

    @pytest.mark.parametrize(
        "marker",
        ["Mensagem ao cliente:", "Mensagem final ao cliente:", "**Resposta para o cliente:**", "mensagem para o cliente"],
    )
    def test_keeps_only_text_after_marker(self, marker):
        text = f"Análise: a peça é 40.\n\n{marker}\nOi! Serve sim."
        assert sanitize_customer_message(text) == "Oi! Serve sim."

    def test_drops_leading_internal_lines_and_separators(self):
        text = "Análise interna: cintura folgada\nFerramentas: compare_fit\n---\n\nOi! Serve com folga."
        assert sanitize_customer_message(text) == "Oi! Serve com folga."

    def test_internal_words_in_the_middle_are_kept(self):
        text = "Oi!\nRaciocínio de estilo: combine com bota."
        assert sanitize_customer_message(text) == text

    def test_never_returns_empty_for_non_empty_input(self):
        assert sanitize_customer_message("   ---   ") == "---"


class TestCitedSkus:
    def test_order_of_first_appearance(self):
        text = "Veja a CAM-2 e depois a CAL-1; a CAM-2 também."
        assert cited_skus(text, ["CAL-1", "CAM-2", "VES-9"]) == ["CAM-2", "CAL-1"]

    def test_whole_code_only(self):
        assert cited_skus("Peça CAM-12 disponível", ["CAM-1"]) == []
        assert cited_skus("Peça XCAM-1 disponível", ["CAM-1"]) == []

    def test_case_insensitive_and_dedupes_input(self):
        assert cited_skus("a cam-1 é linda", ["CAM-1", "CAM-1"]) == ["CAM-1"]

    def test_regex_chars_are_escaped(self):
        assert cited_skus("peça A.1", ["A+1", "A.1"]) == ["A.1"]
        assert cited_skus("peça AX1", ["A.1"]) == []


class TestChunkToText:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (None, ""),
            ("oi", "oi"),
            (["a", "b"], "ab"),
            ([{"type": "text", "text": "a"}, {"type": "tool_use", "id": "x"}, {"text": "b"}], "ab"),
            ([{"type": "text", "text": None}], ""),
            (42, "42"),
        ],
    )
    def test_normalizes(self, content, expected):
        assert chunk_to_text(content) == expected
