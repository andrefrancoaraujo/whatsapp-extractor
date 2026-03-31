"""
Test the backup extraction pipeline end-to-end.
Creates a fake msgstore.db with realistic WhatsApp schema,
then tests the parser and (optionally) the decryptor.
"""

import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from msgstore_parser import parse_msgstore, ParseError


TEST_DIR = Path(__file__).parent / "test_data"


def create_fake_msgstore(db_path: str, num_contacts: int = 8, msgs_per_contact: int = 25):
    """
    Create a fake msgstore.db with realistic WhatsApp Business schema.
    Includes individual chats, groups, media messages, etc.
    """
    # Remove existing test DB
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # ── Create tables matching real WhatsApp schema ──

    c.execute("""
        CREATE TABLE jid (
            _id INTEGER PRIMARY KEY,
            user TEXT,
            server TEXT,
            raw_string TEXT
        )
    """)

    c.execute("""
        CREATE TABLE chat (
            _id INTEGER PRIMARY KEY,
            jid_row_id INTEGER REFERENCES jid(_id),
            subject TEXT,
            hidden INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE message (
            _id INTEGER PRIMARY KEY,
            chat_row_id INTEGER REFERENCES chat(_id),
            from_me INTEGER,
            timestamp INTEGER,
            message_type INTEGER DEFAULT 0,
            text_data TEXT,
            sender_jid_row_id INTEGER REFERENCES jid(_id),
            sort_id INTEGER,
            starred INTEGER DEFAULT 0
        )
    """)

    # ── Populate with realistic data ──

    contacts = [
        ("5511999001001", "s.whatsapp.net", None),       # Individual
        ("5511999002002", "s.whatsapp.net", None),
        ("5511999003003", "s.whatsapp.net", None),
        ("5511988004004", "s.whatsapp.net", None),
        ("5521977005005", "s.whatsapp.net", None),
        ("120363341760876064", "g.us", "Boost Research Geral"),  # Group
        ("120363218842893372", "g.us", "Equipe Marketing"),      # Group
        ("5511966006006", "s.whatsapp.net", None),
    ]

    sample_messages = [
        "Oi, tudo bem?",
        "Bom dia! Tudo certo por ai?",
        "Voce viu o relatorio que mandei?",
        "Vamos marcar uma reuniao pra discutir isso",
        "Perfeito, pode ser amanha as 10h",
        "Obrigado pelo retorno!",
        "Preciso da sua ajuda com um projeto",
        "Ja enviamos o contrato por email",
        "Segue o link do documento",
        "Vou verificar e te retorno em breve",
        "Beleza, combinado!",
        "Temos uma nova proposta para apresentar",
        "O cliente aprovou o orcamento",
        "Fiz as alteracoes que voce pediu",
        "Pode dar uma olhada quando tiver um tempo?",
        "Reuniao confirmada para sexta-feira",
        "Mandei os arquivos no drive",
        "Ficou otimo o trabalho!",
        "Precisamos alinhar os proximos passos",
        "Vou preparar a apresentacao ate amanha",
    ]

    group_messages = [
        "Galera, atencao ao prazo",
        "Alguem pode revisar esse documento?",
        "Reuniao cancelada hoje",
        "Nova meta do trimestre definida",
        "Parabens pela entrega!",
        "Quem fica responsavel por isso?",
        "Agenda da semana atualizada",
        "Deadline estendido para sexta",
    ]

    # Insert JIDs
    jid_ids = {}
    for i, (user, server, _) in enumerate(contacts[:num_contacts], 1):
        raw = f"{user}@{server}"
        c.execute(
            "INSERT INTO jid (_id, user, server, raw_string) VALUES (?, ?, ?, ?)",
            (i, user, server, raw)
        )
        jid_ids[raw] = i

    # Also add some sender JIDs for group messages
    group_senders = [
        ("5511999001001", "s.whatsapp.net"),
        ("5511999002002", "s.whatsapp.net"),
        ("5511988004004", "s.whatsapp.net"),
    ]
    sender_jid_start = num_contacts + 1
    for i, (user, server) in enumerate(group_senders):
        jid_id = sender_jid_start + i
        raw = f"{user}@{server}"
        if raw not in jid_ids:
            c.execute(
                "INSERT INTO jid (_id, user, server, raw_string) VALUES (?, ?, ?, ?)",
                (jid_id, user, server, raw)
            )
            jid_ids[raw] = jid_id

    # Insert chats
    for i, (user, server, subject) in enumerate(contacts[:num_contacts], 1):
        raw = f"{user}@{server}"
        c.execute(
            "INSERT INTO chat (_id, jid_row_id, subject, hidden) VALUES (?, ?, ?, 0)",
            (i, jid_ids[raw], subject)
        )

    # Insert messages
    msg_id = 1
    base_ts = int(time.time() * 1000) - (30 * 24 * 3600 * 1000)  # 30 days ago

    for chat_idx, (user, server, subject) in enumerate(contacts[:num_contacts], 1):
        is_group = server == "g.us"
        msgs = group_messages if is_group else sample_messages
        count = msgs_per_contact + random.randint(-5, 10)

        for j in range(count):
            ts = base_ts + (j * 3600 * 1000) + random.randint(0, 1800000)
            from_me = random.choice([0, 1])
            msg_type = random.choices(
                [0, 0, 0, 0, 0, 1, 2, 3, 8, 20],  # Mostly text, some media
                weights=[50, 50, 50, 50, 50, 10, 5, 5, 3, 2]
            )[0]

            text = random.choice(msgs) if msg_type == 0 else None

            # Sender JID for group messages
            sender_id = None
            if is_group and not from_me:
                sender_raw = random.choice(group_senders)
                sender_id = jid_ids.get(f"{sender_raw[0]}@{sender_raw[1]}")

            c.execute("""
                INSERT INTO message (_id, chat_row_id, from_me, timestamp,
                    message_type, text_data, sender_jid_row_id, sort_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (msg_id, chat_idx, from_me, ts, msg_type, text, sender_id, msg_id))
            msg_id += 1

    # Also insert a hidden chat (should be excluded)
    hidden_jid_id = num_contacts + len(group_senders) + 1
    c.execute(
        "INSERT INTO jid (_id, user, server, raw_string) VALUES (?, ?, ?, ?)",
        (hidden_jid_id, "status", "broadcast", "status@broadcast")
    )
    c.execute(
        "INSERT INTO chat (_id, jid_row_id, subject, hidden) VALUES (?, ?, ?, ?)",
        (num_contacts + 1, hidden_jid_id, "Status Updates", 1)
    )

    conn.commit()
    conn.close()
    return msg_id - 1  # Total messages created


def test_parser():
    """Test the msgstore parser with a fake database."""
    print("=" * 60)
    print("TESTE DO PIPELINE - WhatsApp Backup Extractor")
    print("=" * 60)

    TEST_DIR.mkdir(exist_ok=True)
    db_path = str(TEST_DIR / "msgstore_test.db")

    # Step 1: Create fake database
    print("\n[1/3] Criando banco de dados fake...")
    total_msgs = create_fake_msgstore(db_path, num_contacts=8, msgs_per_contact=25)
    size_kb = os.path.getsize(db_path) / 1024
    print(f"  Criado: {db_path}")
    print(f"  {total_msgs} mensagens, {size_kb:.1f} KB")

    # Step 2: Parse it
    print("\n[2/3] Testando parser...")
    try:
        conversations = parse_msgstore(
            db_path,
            progress_callback=lambda cur, tot, name: print(f"  [{cur}/{tot}] {name}")
        )
    except ParseError as e:
        print(f"  ERRO: {e}")
        return False

    total_parsed = sum(c["message_count"] for c in conversations)
    groups = sum(1 for c in conversations if c.get("is_group"))
    individuals = len(conversations) - groups

    print(f"\n  Resultado:")
    print(f"    {len(conversations)} conversas")
    print(f"    {individuals} individuais, {groups} grupos")
    print(f"    {total_parsed} mensagens parseadas")

    # Step 3: Validate output format
    print("\n[3/3] Validando formato JSON...")
    errors = []

    for conv in conversations:
        # Required fields
        for field in ("contact", "message_count", "messages", "first_message", "last_message"):
            if field not in conv:
                errors.append(f"Campo '{field}' faltando em conversa {conv.get('contact', '?')}")

        # Message format
        if conv["messages"]:
            msg = conv["messages"][0]
            for field in ("date", "time", "sender", "text", "from_me"):
                if field not in msg:
                    errors.append(f"Campo '{field}' faltando em mensagem de {conv['contact']}")

            # Date format DD/MM/YYYY
            if msg["date"] and not all(c.isdigit() or c == "/" for c in msg["date"]):
                errors.append(f"Formato de data invalido: {msg['date']}")

    if errors:
        print("  ERROS encontrados:")
        for e in errors:
            print(f"    - {e}")
        return False

    print("  Formato OK!")

    # Save sample output
    json_path = TEST_DIR / "conversations_test.json"
    json_path.write_text(
        json.dumps(conversations, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n  JSON salvo: {json_path}")

    # Show sample conversation
    print(f"\n  Amostra (primeira conversa):")
    sample = conversations[0]
    print(f"    Contato: {sample['contact_name']}")
    print(f"    Mensagens: {sample['message_count']}")
    print(f"    Periodo: {sample['first_message']} - {sample['last_message']}")
    if sample["messages"]:
        msg = sample["messages"][0]
        print(f"    Primeira: [{msg['date']} {msg['time']}] {msg['sender']}: {msg['text']}")

    print("\n" + "=" * 60)
    print("TODOS OS TESTES PASSARAM!")
    print("=" * 60)
    return True


def test_decryptor_validation():
    """Test the decryptor's input validation (without a real crypt15 file)."""
    from backup_decryptor import validate_hex_key, DecryptionError

    print("\n[Extra] Testando validacao da chave...")

    # Valid key
    valid_key = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    try:
        result = validate_hex_key(valid_key)
        assert result == valid_key
        print(f"  Chave valida: OK")
    except DecryptionError:
        print(f"  ERRO: chave valida rejeitada")
        return False

    # Key with spaces (should normalize)
    spaced_key = "a1b2 c3d4 e5f6 a1b2 c3d4 e5f6 a1b2 c3d4 e5f6 a1b2 c3d4 e5f6 a1b2 c3d4 e5f6 a1b2"
    try:
        result = validate_hex_key(spaced_key)
        print(f"  Chave com espacos: OK (normalizada)")
    except DecryptionError:
        print(f"  ERRO: chave com espacos rejeitada")
        return False

    # Too short
    try:
        validate_hex_key("a1b2c3")
        print(f"  ERRO: chave curta deveria falhar")
        return False
    except DecryptionError:
        print(f"  Chave curta (6 chars): Rejeitada corretamente")

    # Invalid chars
    try:
        validate_hex_key("g" * 64)
        print(f"  ERRO: chave com chars invalidos deveria falhar")
        return False
    except DecryptionError:
        print(f"  Chave com chars invalidos: Rejeitada corretamente")

    print("  Todas as validacoes OK!")
    return True


if __name__ == "__main__":
    ok = test_parser()
    if ok:
        try:
            test_decryptor_validation()
        except ImportError as e:
            print(f"\n[Extra] Pulando teste do decryptor: {e}")
            print("  (wa-crypt-tools sera instalado no build Windows)")
