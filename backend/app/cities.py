"""
The single source of truth for the Myanmar city -> state/zip lookup
used on the complaint form's city autocomplete.

Before this file existed, this list only lived in
frontend/script.js's MYANMAR_CITIES constant - fine for autofilling
the form in the browser, but it meant nothing server-side could
validate a submitted city, and nothing outside the browser bundle
could ever query it. Mirrors app/categories.py's pattern: whichever
code needs this list - server-side validation (app/validation.py), or
the new GET /cities endpoint - imports it from here.

Generated directly from frontend/script.js's existing MYANMAR_CITIES
array (parsed, not retyped by hand, to rule out transcription drift) -
see docs/DECISIONS.md #22. frontend/script.js's own copy is left as-is
for now (a small, explicitly-flagged follow-up would have it fetch
from GET /cities instead - see that same entry for why this pass
didn't also do that).
"""

MYANMAR_CITIES = [
    # Yangon Region
    {"city": "Yangon", "state": "Yangon Region", "zip": "11181"},
    {"city": "Thanlyin", "state": "Yangon Region", "zip": "11291"},
    {"city": "Insein", "state": "Yangon Region", "zip": "11011"},
    {"city": "Hmawbi", "state": "Yangon Region", "zip": "11141"},
    {"city": "Hlegu", "state": "Yangon Region", "zip": "11171"},
    {"city": "Twante", "state": "Yangon Region", "zip": "11241"},
    {"city": "Dala", "state": "Yangon Region", "zip": "11231"},
    {"city": "Shwe Pyi Thar", "state": "Yangon Region", "zip": "11411"},
    # Mandalay Region
    {"city": "Mandalay", "state": "Mandalay Region", "zip": "05011"},
    {"city": "Pyin Oo Lwin", "state": "Mandalay Region", "zip": "05081"},
    {"city": "Meiktila", "state": "Mandalay Region", "zip": "05201"},
    {"city": "Kyaukse", "state": "Mandalay Region", "zip": "05151"},
    {"city": "Myingyan", "state": "Mandalay Region", "zip": "05121"},
    {"city": "Yamethin", "state": "Mandalay Region", "zip": "05231"},
    {"city": "Myittha", "state": "Mandalay Region", "zip": "05191"},
    # Naypyidaw UT
    {"city": "Naypyidaw", "state": "Naypyidaw Union Territory", "zip": "15011"},
    {"city": "Pyinmana", "state": "Naypyidaw Union Territory", "zip": "15021"},
    {"city": "Lewe", "state": "Naypyidaw Union Territory", "zip": "15031"},
    # Shan State
    {"city": "Taunggyi", "state": "Shan State", "zip": "06011"},
    {"city": "Lashio", "state": "Shan State", "zip": "06301"},
    {"city": "Muse", "state": "Shan State", "zip": "06351"},
    {"city": "Kengtung", "state": "Shan State", "zip": "06231"},
    {"city": "Kalaw", "state": "Shan State", "zip": "06021"},
    {"city": "Nyaungshwe", "state": "Shan State", "zip": "06031"},
    {"city": "Hsipaw", "state": "Shan State", "zip": "06311"},
    # Sagaing Region
    {"city": "Sagaing", "state": "Sagaing Region", "zip": "03011"},
    {"city": "Monywa", "state": "Sagaing Region", "zip": "03111"},
    {"city": "Shwebo", "state": "Sagaing Region", "zip": "03021"},
    {"city": "Kale", "state": "Sagaing Region", "zip": "02011"},
    {"city": "Tamu", "state": "Sagaing Region", "zip": "02031"},
    {"city": "Katha", "state": "Sagaing Region", "zip": "03061"},
    # Ayeyarwady Region
    {"city": "Pathein", "state": "Ayeyarwady Region", "zip": "10011"},
    {"city": "Hinthada", "state": "Ayeyarwady Region", "zip": "10021"},
    {"city": "Pyapon", "state": "Ayeyarwady Region", "zip": "10041"},
    {"city": "Bogale", "state": "Ayeyarwady Region", "zip": "10061"},
    {"city": "Maubin", "state": "Ayeyarwady Region", "zip": "10031"},
    {"city": "Chaungtha", "state": "Ayeyarwady Region", "zip": "10071"},
    # Bago Region
    {"city": "Bago", "state": "Bago Region", "zip": "08011"},
    {"city": "Taungoo", "state": "Bago Region", "zip": "08111"},
    {"city": "Pyay", "state": "Bago Region", "zip": "08151"},
    {"city": "Nyaunglebin", "state": "Bago Region", "zip": "08061"},
    {"city": "Letpadan", "state": "Bago Region", "zip": "08181"},
    # Magway Region
    {"city": "Magway", "state": "Magway Region", "zip": "04011"},
    {"city": "Pakokku", "state": "Magway Region", "zip": "04031"},
    {"city": "Minbu", "state": "Magway Region", "zip": "04021"},
    {"city": "Thayet", "state": "Magway Region", "zip": "04111"},
    # Tanintharyi Region
    {"city": "Dawei", "state": "Tanintharyi Region", "zip": "14011"},
    {"city": "Myeik", "state": "Tanintharyi Region", "zip": "14031"},
    {"city": "Kawthaung", "state": "Tanintharyi Region", "zip": "14051"},
    # Mon State
    {"city": "Mawlamyine", "state": "Mon State", "zip": "12011"},
    {"city": "Thaton", "state": "Mon State", "zip": "12031"},
    {"city": "Kyaikto", "state": "Mon State", "zip": "12061"},
    # Kayin State
    {"city": "Hpa-An", "state": "Kayin State", "zip": "13011"},
    {"city": "Myawaddy", "state": "Kayin State", "zip": "13031"},
    # Kayah State
    {"city": "Loikaw", "state": "Kayah State", "zip": "09011"},
    # Chin State
    {"city": "Hakha", "state": "Chin State", "zip": "07011"},
    {"city": "Falam", "state": "Chin State", "zip": "07031"},
    # Kachin State
    {"city": "Myitkyina", "state": "Kachin State", "zip": "01011"},
    {"city": "Bhamo", "state": "Kachin State", "zip": "01031"},
    {"city": "Putao", "state": "Kachin State", "zip": "01051"},
    # Rakhine State
    {"city": "Sittwe", "state": "Rakhine State", "zip": "07011"},
    {"city": "Thandwe", "state": "Rakhine State", "zip": "07111"},
    {"city": "Kyaukphyu", "state": "Rakhine State", "zip": "07131"},]

# Case-insensitive lookup set, used by app/validation.py. Keys are
# lowercased; look up with `city.strip().lower() in CITY_NAMES`.
CITY_NAMES = {entry["city"].lower() for entry in MYANMAR_CITIES}
