
import unittest
import argparse
import csv
import io

from email.message import EmailMessage

from send_mail import generer_message, valider_contact


contacts.csv = """nom\temail\tfilière\tsalle\thoraire
Marie Mornon\tmarie.mornon@etudiant.test\tDUT TIC\tB12\t12h00
Patrick Pierre\tpatrick.pierre@etudiant.test\tDUT TIC\tB12\t16h00
Stéphanie Jolie\tstephanie.Jolie@etudiant.test\tDUT TIC\tA03\t12h00
"""

CHAMPS_REQUIS = [
    "nom",
    "email",
    "filière",
    "salle",
    "horaire",
]


class TestSendMailProject(unittest.TestCase):

    def setUp(self):
        

        self.args = argparse.Namespace(
            subject="Convocation Examen",
            attach=None,
            host="localhost",
            port=1025,
            security="none",
            user="",
            password="",
            dry_run=True,
        )

        self.text_tmpl = (
            "Bonjour {nom},\n"
            "Filière : {filière}\n"
            "Salle : {salle}\n"
            "Horaire : {horaire}\n"
        )

        self.html_tmpl = (
            "<html><body>"
            "<p>Bonjour {nom},</p>"
            "<p>Filière : {filière}</p>"
            "<p>Salle : {salle}</p>"
            "<p>Horaire : {horaire}</p>"
            "</body></html>"
        )

        
        self.contacts = list(
            csv.DictReader(io.StringIO(CSV_CONTACTS), delimiter="\t")
        )

    def test_lecture_csv(self):
        
        self.assertEqual(len(self.contacts), 3)

        for contact in self.contacts:
            for champ in CHAMPS_REQUIS:
                self.assertIn(champ, contact)
                self.assertTrue(contact[champ].strip())

        self.assertEqual(
            self.contacts[0]["nom"], "Marie Mornon"
        )
        self.assertEqual(
            self.contacts[1]["nom"], "Patrick Pierre"
        )
        self.assertEqual(
            self.contacts[2]["nom"], "Stéphanie Jolie"
        )

    def test_validation_des_trois_contacts(self):
        

        for numero, contact in enumerate(self.contacts, start=2):
            with self.subTest(contact=contact["nom"]):
                self.assertTrue(
                    valider_contact(contact, numero)
                )

    def test_validation_contacts_invalides(self):
  

        contact_invalide = {
            "nom": "Étudiant Test",
            "email": "adresse_invalide",
            "filière": "DUT TIC",
            "salle": "B12",
            "horaire": "12h00",
        }

        contact_email_vide = {
            "nom": "Étudiant Test",
            "email": "",
            "filière": "DUT TIC",
            "salle": "B12",
            "horaire": "12h00",
        }

        contact_champ_manquant = {
            "nom": "Étudiant Test",
            "email": "test@etudiant.test",
            "filière": "DUT TIC",
            "salle": "B12",
            "horaire": "",
        }

        self.assertFalse(
            valider_contact(contact_invalide, 1)
        )
        self.assertFalse(
            valider_contact(contact_email_vide, 2)
        )
        self.assertFalse(
            valider_contact(contact_champ_manquant, 3)
        )

    def test_construction_message_mime(self):

        for contact in self.contacts:
            with self.subTest(contact=contact["nom"]):
                msg = generer_message(
                    contact,
                    self.args,
                    self.text_tmpl,
                    self.html_tmpl,
                )

                self.assertIsInstance(msg, EmailMessage)
                self.assertEqual(
                    msg["Subject"], "Convocation Examen"
                )
                self.assertEqual(
                    msg["To"], contact["email"]
                )
                self.assertIsNotNone(msg["From"])

                
                parties = list(msg.walk())
                types_mime = {
                    partie.get_content_type()
                    for partie in parties
                }

                self.assertIn("text/plain", types_mime)
                self.assertIn("text/html", types_mime)

                
                texte = msg.get_body(
                    preferencelist=("plain",)
                ).get_content()

                self.assertIn(contact["nom"], texte)
                self.assertIn(contact["salle"], texte)
                self.assertIn(contact["horaire"], texte)
                self.assertIn(contact["filière"], texte)

    def test_mode_dry_run_serialisation(self):
        """Vérifie la sérialisation sans envoi SMTP."""

        for contact in self.contacts:
            with self.subTest(contact=contact["nom"]):
                msg = generer_message(
                    contact,
                    self.args,
                    self.text_tmpl,
                    self.html_tmpl,
                )

                contenu = msg.as_bytes()

                self.assertIsInstance(contenu, bytes)
                self.assertGreater(len(contenu), 0)
                self.assertIn(
                    contact["email"].encode("ascii"),
                    contenu,
                )

    def test_nombre_et_repartition_des_convocations(self):
        """Vérifie les salles et les horaires des étudiants."""

        attendu = [
            ("Marie Mornon", "B12", "12h00"),
            ("Patrick Pierre", "B12", "16h00"),
            ("Stéphanie Jolie", "A03", "12h00"),
        ]

        obtenu = [
            (c["nom"], c["salle"], c["horaire"])
            for c in self.contacts
        ]

        self.assertEqual(obtenu, attendu)


if __name__ == "__main__":
    unittest.main(verbosity=2)
