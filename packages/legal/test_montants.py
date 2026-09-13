"""La lecture des montants portés sur une facture tunisienne.

Le dinar se divise en mille millimes, et l'usage local écrit cette partie
fractionnaire avec trois décimales : neuf mille cinq cent vingt dinars
s'écrit 9,520.000 ou 9520.000 selon que le millier est séparé ou non. Cette
convention est un piège pour qui lit un nombre à l'européenne, où le point
sépare justement les milliers : un montant de cent sept dinars cent millimes,
écrit 107.100, devient alors cent sept mille cent dinars.

L'erreur n'est pas théorique. Elle multiplie la créance par mille, franchit
tous les seuils du code — celui de cent cinquante dinars qui impose
l'huissier, celui de vingt-cinq mille qui impose l'avocat — et fait
conseiller à une entreprise une procédure sans rapport avec ce qu'elle
réclame. Ces tests fixent donc le comportement attendu avant tout autre
travail sur la fonction.
"""

from __future__ import annotations

import pytest

from packages.legal.invoice import _to_float, find_amount


class TestPartieFractionnaireTunisienne:
    """Trois décimales après un point : ce sont des millimes, pas des milliers."""

    def test_cent_sept_dinars_cent_millimes(self):
        # Le cas qui a révélé le défaut : une réparation de deux tabourets,
        # facturée cent sept dinars et cent millimes. Lue comme cent sept
        # mille cent dinars, elle dépassait le seuil de l'avocat obligatoire.
        assert _to_float("107.100") == pytest.approx(107.100)

    def test_montant_rond_a_trois_decimales(self):
        assert _to_float("9520.000") == pytest.approx(9520.0)

    def test_petit_montant_sous_le_seuil_de_l_huissier(self):
        # Sous cent cinquante dinars, la sommation n'a pas à être signifiée
        # par un huissier de justice. Se tromper ici change le conseil rendu.
        assert _to_float("149.500") == pytest.approx(149.5)

    def test_millimes_non_nuls(self):
        assert _to_float("1800.750") == pytest.approx(1800.75)


class TestSeparateurDeMilliers:
    """La virgule sépare les milliers, le point les millimes."""

    def test_virgule_millier_et_point_millime(self):
        assert _to_float("9,520.000") == pytest.approx(9520.0)

    def test_deux_separateurs_de_milliers(self):
        assert _to_float("1,234,567.500") == pytest.approx(1234567.5)

    def test_virgule_seule_en_separateur_de_milliers(self):
        # Sans partie fractionnaire, la virgule reste un séparateur de
        # milliers : quarante-sept mille trois cent soixante-deux dinars.
        assert _to_float("47,362") == pytest.approx(47362.0)


class TestConventionEuropeenne:
    """Une facture peut aussi arriver rédigée à la française."""

    def test_virgule_decimale_deux_chiffres(self):
        assert _to_float("1234,56") == pytest.approx(1234.56)

    def test_point_millier_et_virgule_decimale(self):
        assert _to_float("1.234,56") == pytest.approx(1234.56)


class TestCasSimples:
    def test_entier_nu(self):
        assert _to_float("9520") == pytest.approx(9520.0)

    def test_deux_decimales_apres_un_point(self):
        # Deux décimales ne peuvent pas être un séparateur de milliers :
        # c'est une partie fractionnaire, quelle que soit la convention.
        assert _to_float("107.10") == pytest.approx(107.10)

    def test_espaces_autour(self):
        assert _to_float("  9520.000  ") == pytest.approx(9520.0)

    def test_espace_separateur_de_milliers(self):
        assert _to_float("9 520.000") == pytest.approx(9520.0)


class TestEntreesHostiles:
    """Ce qui n'est pas un nombre ne doit pas devenir un nombre."""

    @pytest.mark.parametrize("entree", ["", "   ", "abc", "-", ".", ",",
                                        "12.34.56.78", "1..2"])
    def test_rend_rien_plutot_qu_un_chiffre_invente(self, entree):
        assert _to_float(entree) is None


class TestLectureSurLaFacture:
    """La fonction qui choisit le montant sur la ligne du total."""

    def test_net_a_payer_avec_millimes(self):
        texte = (
            "Réparation de deux tabourets 2 45.000 90.000\n"
            "TOTAL HT 90.000\n"
            "TVA 19% 17.100\n"
            "NET A PAYER 107.100\n"
        )
        assert find_amount(texte) == pytest.approx(107.100)

    def test_net_a_payer_avec_separateur_de_milliers(self):
        texte = (
            "TOTAL HT 8,000.000\n"
            "TVA 19% 1,520.000\n"
            "NET A PAYER 9,520.000\n"
        )
        assert find_amount(texte) == pytest.approx(9520.0)

    def test_gros_montant_au_dessus_du_seuil_de_l_avocat(self):
        # Au-delà de vingt-cinq mille dinars, la représentation par avocat
        # devient obligatoire : le montant doit être lu exactement.
        texte = "NET A PAYER 47,362.000\n"
        assert find_amount(texte) == pytest.approx(47362.0)
