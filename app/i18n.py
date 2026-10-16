"""Fixed strings that appear *inside the book* (not the application UI), by book language.

Anything the reader sees that the app generates itself (for example "(continued)" on a poem that runs
onto the next page) follows the book's language code. Unknown languages fall back to English.
"""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "continued": {"en": "(continued)", "ro": "(continuare)", "fr": "(suite)", "de": "(Fortsetzung)",
                  "es": "(continuación)", "it": "(continua)", "pt": "(continuação)",
                  "hu": "(folytatás)", "pl": "(ciąg dalszy)", "nl": "(vervolg)"},
    "contents": {"en": "Contents", "ro": "Cuprins", "fr": "Table des matières", "de": "Inhalt",
                 "es": "Índice", "it": "Indice", "pt": "Índice", "hu": "Tartalom", "pl": "Spis treści",
                 "nl": "Inhoud"},
    "poem_index": {"en": "Index of poems", "ro": "Index de poezii", "fr": "Index des poèmes",
                   "de": "Gedichtverzeichnis", "es": "Índice de poemas", "it": "Indice delle poesie",
                   "pt": "Índice de poemas", "hu": "Versek jegyzéke", "pl": "Spis wierszy",
                   "nl": "Gedichtenindex"},
    "chapter": {"en": "Chapter", "ro": "Capitolul", "fr": "Chapitre", "de": "Kapitel", "es": "Capítulo",
                "it": "Capitolo", "pt": "Capítulo", "hu": "Fejezet", "pl": "Rozdział", "nl": "Hoofdstuk"},
    "part": {"en": "Part", "ro": "Partea", "fr": "Partie", "de": "Teil", "es": "Parte", "it": "Parte",
             "pt": "Parte", "hu": "Rész", "pl": "Część", "nl": "Deel"},
    "notes": {"en": "Notes", "ro": "Note", "fr": "Notes", "de": "Anmerkungen", "es": "Notas", "it": "Note",
              "pt": "Notas", "hu": "Jegyzetek", "pl": "Przypisy", "nl": "Noten"},
    "ingredients": {"en": "Ingredients", "ro": "Ingrediente", "fr": "Ingrédients", "de": "Zutaten",
                    "es": "Ingredientes", "it": "Ingredienti", "pt": "Ingredientes", "hu": "Hozzávalók",
                    "pl": "Składniki", "nl": "Ingrediënten"},
    "method": {"en": "Method", "ro": "Mod de preparare", "fr": "Préparation", "de": "Zubereitung",
               "es": "Preparación", "it": "Preparazione", "pt": "Modo de preparo", "hu": "Elkészítés",
               "pl": "Przygotowanie", "nl": "Bereiding"},
    "prep": {"en": "Prep", "ro": "Pregătire", "fr": "Préparation", "de": "Vorbereitung", "es": "Preparación",
             "it": "Preparazione", "pt": "Preparo", "hu": "Előkészítés", "pl": "Przygotowanie", "nl": "Voorbereiding"},
    "cook": {"en": "Cook", "ro": "Gătire", "fr": "Cuisson", "de": "Garzeit", "es": "Cocción", "it": "Cottura",
             "pt": "Cozimento", "hu": "Főzés", "pl": "Gotowanie", "nl": "Bereidingstijd"},
    "serves": {"en": "Serves", "ro": "Porții", "fr": "Portions", "de": "Portionen", "es": "Raciones",
               "it": "Porzioni", "pt": "Porções", "hu": "Adag", "pl": "Porcje", "nl": "Porties"},
    "recipe_notes": {"en": "Notes", "ro": "Note", "fr": "Notes", "de": "Hinweise", "es": "Notas", "it": "Note",
                     "pt": "Notas", "hu": "Megjegyzés", "pl": "Uwagi", "nl": "Opmerkingen"},
    "nutrition": {"en": "Nutrition (as supplied)", "ro": "Valori nutriționale (furnizate de autor)",
                  "fr": "Valeurs nutritionnelles (fournies)", "de": "Nährwerte (angegeben)",
                  "es": "Información nutricional (aportada)", "it": "Valori nutrizionali (forniti)",
                  "pt": "Informação nutricional (fornecida)", "hu": "Tápérték (megadva)",
                  "pl": "Wartości odżywcze (podane)", "nl": "Voedingswaarde (opgegeven)"},
    "k_objective": {"en": "Learning objective", "ro": "Obiectiv de învățare", "fr": "Objectif",
                    "de": "Lernziel", "es": "Objetivo", "it": "Obiettivo"},
    "k_definition": {"en": "Definition", "ro": "Definiție", "fr": "Définition", "de": "Definition",
                     "es": "Definición", "it": "Definizione"},
    "k_example": {"en": "Example", "ro": "Exemplu", "fr": "Exemple", "de": "Beispiel", "es": "Ejemplo", "it": "Esempio"},
    "k_exercise": {"en": "Exercise", "ro": "Exercițiu", "fr": "Exercice", "de": "Übung", "es": "Ejercicio",
                   "it": "Esercizio"},
    "k_question": {"en": "Question", "ro": "Întrebare", "fr": "Question", "de": "Frage", "es": "Pregunta",
                   "it": "Domanda"},
    "k_answer": {"en": "Answer", "ro": "Răspuns", "fr": "Réponse", "de": "Antwort", "es": "Respuesta",
                 "it": "Risposta"},
    "k_note": {"en": "Note", "ro": "Notă", "fr": "Remarque", "de": "Hinweis", "es": "Nota", "it": "Nota"},
    "k_warning": {"en": "Warning", "ro": "Atenție", "fr": "Attention", "de": "Achtung", "es": "Advertencia",
                  "it": "Attenzione"},
    "k_reference": {"en": "Reference", "ro": "Referință", "fr": "Référence", "de": "Verweis",
                    "es": "Referencia", "it": "Riferimento"},
}


def lang_code(language: str | None) -> str:
    return (language or "en").replace("_", "-").split("-")[0].lower() or "en"


def tr(key: str, language: str | None) -> str:
    table = STRINGS[key]
    return table.get(lang_code(language)) or table["en"]


def exercise_label(kind: str, language: str | None) -> str:
    key = f"k_{kind}"
    return tr(key, language) if key in STRINGS else kind.title()
