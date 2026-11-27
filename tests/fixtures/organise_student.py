"""A made-up student for ORGANISE-1 (2026-11-26): 300 notes and files from a laptop, 40 old AI chats, three
languages. Mira studies in Germany (course notes in German), asks ChatGPT in English, and keeps her own life
in Russian. Nothing here is anyone's data.

Each item is what api/organise.PgStore.items returns: name, kind, title, summary, date, private, vec. The
embeddings stand in for a multilingual model: one direction per subject plus noise, the same direction for a
German note and an English chat on the same subject (that is what lets old chats and laptop files meet).
`truth` is the subject each item was made from, for the test's purity check only.
"""
import random

SUBJECTS = {
    "bio": {"folder": "Uni/Biologie", "lang": "de",
            "titles": ["Zellbiologie Vorlesung {n}", "Mitose und Meiose", "Genetik Übung {n}", "Photosynthese Zusammenfassung",
                       "Enzyme Protokoll {n}", "Evolution Skript Kapitel {n}", "Zellmembran Transport", "Ökologie Klausur Vorbereitung"],
            "words": "Zelle Membran Protein Enzym Gen DNA Mitose Chromosom Photosynthese Evolution Organismus",
            "chats": ["Explain cell membrane transport simply", "Difference between mitosis and meiosis",
                      "Help me memorise the Krebs cycle", "Photosynthesis light reactions question", "How do enzymes lower activation energy",
                      "DNA replication steps for my exam", "Evolution essay outline natural selection"]},
    "hist": {"folder": "Uni/Geschichte", "lang": "de",
             "titles": ["Weimarer Republik Seminar {n}", "Französische Revolution Notizen", "Kalter Krieg Referat",
                        "Quellenanalyse {n}", "Industrialisierung Vorlesung {n}", "Hausarbeit Gliederung Reichsgründung", "Mittelalter Skript {n}"],
             "words": "Revolution Republik Krieg Reich Quelle Epoche Kaiser Verfassung Industrialisierung Seminar",
             "chats": ["Causes of the French Revolution summary", "Weimar Republic hyperinflation 1923",
                       "Cold War timeline for a presentation", "How to analyse a historical source", "Industrial revolution in Germany",
                       "Structure for my history term paper"]},
    "math": {"folder": "Uni/Mathe", "lang": "de",
             "titles": ["Lineare Algebra Blatt {n}", "Analysis Übung {n}", "Eigenwerte Zusammenfassung", "Integralrechnung Formeln",
                        "Statistik Tutorium {n}", "Beweise Induktion", "Matrizen Lösungen {n}"],
             "words": "Matrix Vektor Integral Ableitung Eigenwert Beweis Funktion Grenzwert Statistik Wahrscheinlichkeit",
             "chats": ["Eigenvalues of a 3x3 matrix step by step", "Proof by induction example", "Integration by parts trick",
                       "What is a confidence interval", "Linear independence explained", "Limit of a sequence homework",
                       "Bayes theorem with an example"]},
    "econ": {"folder": "Uni/VWL", "lang": "de",
             "titles": ["Mikroökonomie Vorlesung {n}", "Angebot und Nachfrage", "Makro Klausur {n}", "Inflation Geldpolitik",
                        "Spieltheorie Übung {n}", "Marktformen Zusammenfassung"],
             "words": "Markt Preis Nachfrage Angebot Inflation Geldpolitik Zins Wachstum Elastizität Monopol",
             "chats": ["Price elasticity of demand example", "Why does inflation happen", "Nash equilibrium in simple terms",
                       "Monopoly vs perfect competition", "ECB interest rates and inflation", "Supply and demand graph shifts"]},
    "personal": {"folder": "Личное", "lang": "ru",
                 "titles": ["Дневник {n}", "Рецепт борщ", "Поездка в Прагу план", "Список покупок {n}", "Письмо бабушке",
                            "Тренировки зал {n}", "Мысли перед сессией", "Подарки на день рождения"],
                 "words": "дневник рецепт поездка бабушка мама подарок тренировка покупки квартира друзья",
                 "chats": ["Plan a cheap weekend trip to Prague", "Workout plan three days a week", "Birthday gift ideas for grandma",
                           "Help me write a letter to my landlord", "Budget for a student month", "Borscht recipe vegetarian",
                           "How to sleep better before exams", "Apartment search tips in Berlin"]},
    "work": {"folder": "Job/Werkstudent", "lang": "de",
             "titles": ["Werkstudent Vertrag", "Stundenzettel {n}", "Meeting Notizen Marketing {n}", "Bewerbung Anschreiben {n}",
                      "Lebenslauf", "Praktikum Bericht"],
             "words": "Bewerbung Lebenslauf Praktikum Meeting Kunde Projekt Stunden Vertrag Marketing Team",
             "chats": ["Improve my CV for a marketing internship", "Cover letter for a working student job",
                       "Agenda for a weekly team meeting", "How to ask for a raise as a student", "Interview questions marketing"]},
    "school": {"folder": "Schule/Abitur 2019", "lang": "de",
               "titles": ["Abitur Deutsch Aufsatz 2019", "Facharbeit Chemie 2019", "Englisch Vokabeln 2018", "Klassenfahrt 2019 Fotos Liste",
                          "Physik Referat 2018", "Abschlussball 2019 Planung"],
               "words": "Abitur Schule Klasse Lehrer Facharbeit Aufsatz Klassenfahrt Abschlussball",
               "chats": []},
}

# how many laptop notes per subject (sums to 300) and chats (sums to 40)
NOTES = {"bio": 60, "hist": 45, "math": 55, "econ": 40, "personal": 45, "work": 25, "school": 30}
CHATS = {"bio": 8, "hist": 6, "math": 8, "econ": 6, "personal": 8, "work": 4, "school": 0}

EXT = ["md", "pdf", "docx", "txt"]


def _vec(rng, centre, dim, noise):
    return [c + rng.gauss(0, noise) for c in centre]


def student(seed: int = 7, dim: int = 64, noise: float = 0.35, with_vec: bool = True):
    rng = random.Random(seed)
    centres = {s: [rng.gauss(0, 1) for _ in range(dim)] for s in SUBJECTS}
    items, truth = [], {}
    for s, n in NOTES.items():
        spec = SUBJECTS[s]
        words = spec["words"].split()
        for i in range(n):
            t = rng.choice(spec["titles"]).format(n=i + 1)
            sub = rng.choice(["", "", "Semester 3/", "Alt/"]) if s not in ("personal", "school") else ""
            ext = rng.choice(EXT)
            name = f"laptop/Documents/{spec['folder']}/{sub}{t.replace(' ', '_')}_{i}.{ext}"
            if s == "school":
                year = rng.choice(["2018", "2019"])
                date = f"{year}-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}"
            else:
                date = None
            if s == "personal" and i % 5 == 0:
                t = f"{t} (private {i})"   # a title of its own, so the test can tell it never reaches the namer
            summary = " ".join(rng.sample(words, 5))
            it = {"name": name, "kind": "doc", "title": t, "summary": summary, "date": date, "private": s == "personal" and i % 5 == 0,
                  "vec": _vec(rng, centres[s], dim, noise) if with_vec else None}
            items.append(it); truth[name] = s
    for s, n in CHATS.items():
        spec = SUBJECTS[s]
        for i in range(n):
            t = spec["chats"][i % len(spec["chats"])]
            name = f"chatgpt_{t.lower().replace(' ', '-')[:40]}-{i}.md"
            date = f"2026-{rng.randint(1, 10):02d}-{rng.randint(10, 28)}"
            it = {"name": name, "kind": "chat", "title": t, "summary": f"First ask: {t}. Last ask: thanks.",
                  "date": date, "private": False, "vec": _vec(rng, centres[s], dim, noise) if with_vec else None}
            items.append(it); truth[name] = s
    rng.shuffle(items)
    return items, truth
