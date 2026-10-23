# TIC550 - Devoir 2 : Outil de Messagerie SMTP et Client Sockets

Il y a deux application Python :
1. `send_mail.py` : Un script de publipostage gérant les courriels alternatifs au format MIME, des pièces jointes, de la validation des contacts CSV, du mode simulation et du rapport d'envoi.
2. `smtp_raw.py` : Un mini-client SMTP qui utilise des sockets TCP pour les commandes du protocole SMTP et leur échanges.
   
Installation et Déploiement du Serveur de Test

. Emploi de --Mailpit-- afin capturer les courriels localement dans leur integralite et sans distribution

```bash
docker-compose up -d
```
8025 : Comme interface Web permettant de consulter les courriels capturés.
Soit : http://localhost:8025

Si docker ne fonctionne pas:

```bash
python -m pip aiosmtpd 
```

Puis: 

```bash
python -m aiosmtpd -n -l localhost:1025
```

Pour installer les dépendances 

```bash
pip install -r requirements.txt
```

ou

```bash
python -m pip install -r requirements.txt
```

-Exemples d'Exécution en simulation-

Création de fichiers `.eml` locaux

```bash
python send_mail.py --csv data/contacts.csv --subject "Convocation Examen Officiel" --dry-run
```

3. Pour Exécuter le Client SMTP Brut
```bash   
python smtp_raw.py
```

-Pour tester Automatique-
```bash
pytest -v
```
