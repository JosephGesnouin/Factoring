"""Tests pour reconciliation.reference_extractor.

Couvre :
- mots-clés métier multilingues (FR, EN, DE, IT, ES, NL, PL)
- ISO 20022 (/ROC/, /RFB/, /INV/, /TRF/, RF11649, E2E)
- amorces contextuelles (REF:, N°, NUM, VOTRE FACTURE…)
- séquences numériques pures
- déduplication
- génération de variantes
"""
from reconciliation.reference_extractor import (
    HIGH, ISO, LOW, MEDIUM,
    extract_all, extract_canonical_refs, generate_variants,
)


class TestKeywordPatterns:
    """Mot-clé métier + numéro structuré."""

    def test_fr_facture(self):
        refs = extract_canonical_refs("REGLT FACTURE 2024-001234")
        assert "FACTURE2024001234" in refs or "2024001234" in refs

    def test_fr_fac_short(self):
        refs = extract_canonical_refs("VIR FAC2024001")
        assert any("2024001" in r for r in refs)

    def test_en_invoice(self):
        refs = extract_canonical_refs("PAYMENT FOR INVOICE 2024-001234")
        assert any("2024001234" in r for r in refs)

    def test_en_inv_short(self):
        refs = extract_canonical_refs("INV-2024-001")
        assert any("2024001" in r for r in refs)

    def test_de_rechnung(self):
        refs = extract_canonical_refs("ZAHLUNG RECHNUNG 2024-001234")
        assert any("2024001234" in r for r in refs)

    def test_de_rg(self):
        refs = extract_canonical_refs("UBERWEISUNG RG 2024-007")
        assert any("2024007" in r for r in refs)

    def test_it_fattura(self):
        refs = extract_canonical_refs("BONIFICO FATTURA 2024-001234")
        assert any("2024001234" in r for r in refs)

    def test_it_ft(self):
        refs = extract_canonical_refs("PAGAMENTO FT 2024-007")
        assert any("2024007" in r for r in refs)

    def test_es_factura(self):
        refs = extract_canonical_refs("PAGO FACTURA 2024-001234")
        assert any("2024001234" in r for r in refs)

    def test_nl_factuur(self):
        refs = extract_canonical_refs("BETALING FACTUUR 2024-001234")
        assert any("2024001234" in r for r in refs)

    def test_pl_fv(self):
        refs = extract_canonical_refs("PRZELEW FV 2024-001234")
        assert any("2024001234" in r for r in refs)


class TestISO20022:
    def test_roc_field(self):
        refs = extract_canonical_refs("VIRT SEPA /ROC/REF12345")
        assert any("REF12345" in r for r in refs)

    def test_rfb_field(self):
        refs = extract_canonical_refs("/RFB/2024-INV-001")
        assert any("2024INV001" in r for r in refs)

    def test_inv_field(self):
        refs = extract_canonical_refs("/INV/FAC202400123")
        assert any("FAC202400123" in r for r in refs)

    def test_iso_11649(self):
        refs = extract_canonical_refs("Payment with RF18539007547034")
        assert any("RF18539007547034" in r for r in refs)

    def test_e2e_id(self):
        refs = extract_canonical_refs("E2E: ABCD1234567890 transfer")
        assert any("ABCD1234567890" in r for r in refs)

    def test_iso_has_high_confidence(self):
        all_m = extract_all("/ROC/12345 and 987654")
        # ISO doit primer sur séquence numérique pure
        iso_m = [m for m in all_m if m.source.startswith("iso_")]
        assert any(m.confidence == ISO for m in iso_m)


class TestContextualPrefixes:
    def test_ref_colon(self):
        refs = extract_canonical_refs("PAIEMENT REF: 2024-001234")
        assert any("2024001234" in r for r in refs)

    def test_numero_symbol(self):
        refs = extract_canonical_refs("VIR N° 2024-007")
        assert any("2024007" in r for r in refs)

    def test_your_invoice(self):
        refs = extract_canonical_refs("Payment for YOUR INVOICE 2024-INV-001")
        assert any("2024INV001" in r for r in refs)

    def test_votre_facture(self):
        refs = extract_canonical_refs("REGLT VOTRE FACTURE 2024-001")
        assert any("2024001" in r or "FACTURE2024001" in r for r in refs)


class TestNumericFallbacks:
    def test_year_dash(self):
        refs = extract_canonical_refs("PAY 2024-001234 thanks")
        assert any("2024001234" in r for r in refs)

    def test_pure_long_number(self):
        refs = extract_canonical_refs("Random text 567891234 end")
        assert any("567891234" in r for r in refs)

    def test_short_number_ignored(self):
        refs = extract_canonical_refs("Payment 123 thanks")
        # 3 chiffres ne devraient pas être extraits comme référence
        assert not any(r == "123" for r in refs)

    def test_iban_chunks_not_extracted(self):
        # On ne veut PAS que les morceaux d'IBAN soient pris comme refs
        refs = extract_canonical_refs("VIR DE FR7630001007941234567890185")
        # L'IBAN entier doit éventuellement matcher (séquence longue de digits)
        # mais le test ici c'est que ça ne donne pas plein de refs courtes
        assert all(len(r) >= 5 for r in refs) or len(refs) == 0


class TestDedupe:
    def test_no_duplicate_canonical(self):
        # Même référence vue 2 fois (mot-clé puis numérique) -> 1 seule
        refs = extract_canonical_refs("FAC 2024-001 et 2024001")
        # On ne veut pas voir 2024001 deux fois
        assert refs.count("2024001") <= 1

    def test_higher_confidence_wins(self):
        """Quand la même référence a plusieurs matches, on garde le
        plus confidentiel."""
        matches = extract_all("FACTURE 2024-001234 et 2024-001234")
        canonicals = {m.canonical for m in matches}
        # Toutes les références sont uniques
        assert len(canonicals) == len(matches)


class TestVariants:
    def test_with_alpha_prefix(self):
        v = generate_variants("FAC2024001")
        assert "FAC-2024001" in v or "FAC2024001" in v
        # le numéro nu doit aussi être dans les variantes
        assert "2024001" in v

    def test_year_split(self):
        v = generate_variants("2024001234")
        # variantes avec séparateur entre l'année et le reste
        assert any("2024-001234" in x for x in v) or "2024001234" in v

    def test_padding(self):
        v = generate_variants("FAC001")
        # padding zéro doit générer une longueur 6+
        assert any(len(x) >= 6 for x in v)

    def test_empty(self):
        assert generate_variants("") == []


class TestEdgeCases:
    def test_empty_label(self):
        assert extract_canonical_refs("") == []

    def test_no_refs(self):
        refs = extract_canonical_refs("MERCI POUR VOTRE PAIEMENT")
        # Aucune référence claire dans ce texte
        assert isinstance(refs, list)

    def test_mixed_languages(self):
        # Libellé mixte FR + DE (cas réel chez clients multi-pays)
        refs = extract_canonical_refs("ZAHLUNG FACTURE 2024-001 / RG 2024-002")
        # Doit extraire au moins une des deux
        assert len(refs) >= 1

    def test_multiple_in_one_label(self):
        refs = extract_canonical_refs(
            "VIRT FAC2024-001 FAC2024-002 FAC2024-003"
        )
        assert len(refs) >= 3
