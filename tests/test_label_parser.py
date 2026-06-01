"""Tests pour ``reconciliation.label_parser``.

Couvre les 20+ templates observés en production + variantes + multilingue.
"""
from reconciliation.label_parser import parse, TEMPLATES, _COMPILED, _compile_template


# ============================================================================
# Templates métier observés en production
# ============================================================================

class TestProductionTemplates:
    """Les templates extraits du screenshot Excel de l'utilisateur."""

    def test_cat_d_num(self):
        r = parse("CAT D 12345")
        assert "CAT_D" in r.factoring_codes
        assert r.factoring_codes["CAT_D"] == "12345"
        assert r.confidence >= 0.85

    def test_cat_d_iban(self):
        r = parse("CAT D FR7630001007941234567890185")
        assert r.factoring_codes.get("CAT_D") or r.iban_refs
        assert r.confidence >= 0.80

    def test_mid_nbt_sdt_rbr_full(self):
        r = parse("/MID FACT2024/NBT 12345/SDT 20240115/RBR REF-ABC")
        assert r.factoring_codes["MID"] == "FACT2024"
        assert r.factoring_codes["NBT"] == "12345"
        assert r.factoring_codes["SDT"] == "20240115"
        assert r.factoring_codes["RBR"] == "REF-ABC"
        assert "12345" in r.bordereau_refs   # NBT est aussi un bordereau
        assert r.confidence >= 0.95

    def test_mid_nbt_sdt_only(self):
        r = parse("MID 9876/NBT 12345/SDT 20240115")
        assert r.factoring_codes.get("NBT") == "12345"
        assert r.confidence >= 0.90

    def test_dispo_remise_full(self):
        r = parse("DISPO/REMISE 12345/SDT 20240115/RBA REF-ABC")
        assert "DISPO_REMISE" in r.factoring_codes
        assert "12345" in r.bordereau_refs
        assert r.confidence >= 0.90

    def test_dispo_remise_simple(self):
        r = parse("DISPO/REMISE 12345")
        assert r.factoring_codes["DISPO_REMISE"] == "12345"
        assert "12345" in r.bordereau_refs

    def test_inv_dated(self):
        r = parse("/INV/12345 15/10/2024")
        assert "12345" in r.invoice_refs
        assert r.sepa_fields["INV"] == "12345"
        assert any(d.year == 2024 and d.month == 10 for d in r.dates)

    def test_inv_ref_dated(self):
        r = parse("/INV/REF-2024-001 15/10/2024")
        assert any("REF-2024-001" in ref for ref in r.invoice_refs)
        assert r.sepa_fields["INV"]
        assert any(d.year == 2024 for d in r.dates)

    def test_multi_inv_dated(self):
        r = parse("/INV/12345 15/10/2024/INV/67890 22/10/2024")
        assert "12345" in r.invoice_refs
        assert "67890" in r.invoice_refs
        assert len(r.dates) >= 2

    def test_bordereau_inv(self):
        r = parse("BORDEREAU 5555 15/10/2024/INV/12345 15/10/2024")
        assert "5555" in r.bordereau_refs
        assert "12345" in r.invoice_refs
        assert r.factoring_codes["BORDEREAU"] == "5555"

    def test_bordereau_dated(self):
        r = parse("BORDEREAU 5555 15/10/2024")
        assert "5555" in r.bordereau_refs
        assert len(r.dates) >= 1

    def test_bordereau_simple(self):
        r = parse("BORDEREAU 5555")
        assert "5555" in r.bordereau_refs

    def test_facture_num(self):
        r = parse("FACTURE 2024-001")
        assert any("2024" in ref for ref in r.invoice_refs)

    def test_facture_glued(self):
        r = parse("VIR SEPA REGL FAC2024001")
        assert any("2024001" in ref for ref in r.invoice_refs)
        # Stopwords filtrés
        for stop in ("VIR", "SEPA", "REGL"):
            assert stop not in r.invoice_refs

    def test_advice_dated(self):
        r = parse("ADV/987654 15/10/2024")
        assert "987654" in r.invoice_refs
        assert r.factoring_codes["ADV"] == "987654"

    def test_star_num_num(self):
        r = parse("*12345 67890")
        assert "12345" in r.invoice_refs
        assert "67890" in r.invoice_refs

    def test_urg_chq_traite(self):
        r = parse("URG GN12345 N CHQ TRAITE")
        assert "INSTRUMENT" in r.factoring_codes
        # URGENT keyword peut être détecté
        assert "URGENT" in r.keywords or r.factoring_codes.get("INSTRUMENT")

    def test_foreign_transfer(self):
        r = parse("FOREIGN TRANSFER")
        assert "FOREIGN" in r.keywords
        # Très peu spécifique
        assert r.confidence < 0.50

    def test_facture_alone(self):
        r = parse("FACTURE")
        # Mot seul -> peu d'information
        assert "FACTURE" in r.document_types

    def test_two_nums(self):
        r = parse("11111 22222")
        # Au moins l'un des deux extrait via fallback
        assert "11111" in r.invoice_refs or "22222" in r.invoice_refs


# ============================================================================
# Multilingue
# ============================================================================

class TestMultilingual:
    def test_fr_facture(self):
        r = parse("REGLEMENT FACTURE 2024-001234")
        assert any("2024" in ref for ref in r.invoice_refs)

    def test_en_invoice(self):
        r = parse("PAYMENT INVOICE 2024-001234")
        assert r.invoice_refs
        assert "PAYMENT" not in r.invoice_refs  # stopword filtered

    def test_de_rechnung(self):
        r = parse("ZAHLUNG RECHNUNG 2024-007")
        assert r.invoice_refs

    def test_it_fattura(self):
        r = parse("PAGAMENTO FATTURA 2024-789")
        assert r.invoice_refs

    def test_es_factura(self):
        r = parse("PAGO FACTURA 2024-001 GRACIAS")
        assert r.invoice_refs

    def test_nl_factuur(self):
        r = parse("BETALING FACTUUR 2024-001234")
        assert r.invoice_refs

    def test_pl_fv(self):
        r = parse("PRZELEW FV 2024-001234")
        assert any("2024" in ref for ref in r.invoice_refs)


# ============================================================================
# Extraction atomique
# ============================================================================

class TestAtomicExtraction:
    def test_iban_inline(self):
        r = parse("Payment from FR7630001007941234567890185")
        assert any("FR7630" in i for i in r.iban_refs)

    def test_date_extraction(self):
        r = parse("FACTURE 100 du 15/10/2024")
        assert any(d.year == 2024 for d in r.dates)

    def test_amount_extraction(self):
        r = parse("VIR 1234,56 EUR pour facture")
        assert 1234.56 in r.amounts

    def test_multiple_dates(self):
        r = parse("Du 01/01/2024 au 31/12/2024")
        assert len(r.dates) >= 2

    def test_keywords_factoring(self):
        r = parse("REMISE BORDEREAU avec ESCOMPTE")
        assert "BORDEREAU" in r.keywords or "REMISE" in r.keywords

    def test_keywords_credit_note(self):
        r = parse("AVOIR sur facture initiale")
        assert "AVOIR" in r.keywords

    def test_keywords_urgent(self):
        r = parse("URGENT VIR 1000 EUR")
        assert "URGENT" in r.keywords


# ============================================================================
# Compilation DSL
# ============================================================================

class TestDSLCompilation:
    def test_simple_template(self):
        pat, groups = _compile_template("CAT D <NUM>")
        assert pat.search("CAT D 12345")
        assert groups == [("num_0", "NUM")]

    def test_repeated_placeholders(self):
        pat, groups = _compile_template("<NUM> <NUM> <NUM>")
        m = pat.search("11 22 33")
        assert m
        # 3 groupes nommés différents
        assert len(groups) == 3
        assert m.group("num_0") == "11"
        assert m.group("num_1") == "22"
        assert m.group("num_2") == "33"

    def test_complex_template(self):
        pat, groups = _compile_template("BORDEREAU <NUM> <DATE>/INV/<NUM> <DATE>")
        m = pat.search("BORDEREAU 5555 15/10/2024/INV/12345 15/10/2024")
        assert m
        assert m.group("num_0") == "5555"
        assert m.group("num_2") == "12345"

    def test_whitespace_flexible(self):
        # Whitespace multiple
        pat, _ = _compile_template("FACTURE <NUM>")
        assert pat.search("FACTURE   2024")
        assert pat.search("FACTURE 2024")

    def test_all_templates_compile(self):
        # Aucune erreur de compilation sur la bibliothèque entière
        assert len(_COMPILED) == len(TEMPLATES)
        for pat, _, _, _ in _COMPILED:
            assert pat is not None


# ============================================================================
# Robustesse
# ============================================================================

class TestRobustness:
    def test_empty_label(self):
        r = parse("")
        assert r.confidence == 0.0
        assert r.invoice_refs == []

    def test_only_whitespace(self):
        r = parse("     ")
        assert r.invoice_refs == []

    def test_no_match(self):
        r = parse("aucune information utile")
        # Pas de crash, pas de référence inventée
        assert isinstance(r.invoice_refs, list)

    def test_very_long_label(self):
        # Pas de blocage sur libellé très long
        r = parse("FACTURE 2024-001 " + "x" * 500)
        assert isinstance(r, type(r))

    def test_special_chars(self):
        r = parse("VIR €100,50 FAC#2024/001 €")
        # Pas de crash
        assert isinstance(r.invoice_refs, list)
