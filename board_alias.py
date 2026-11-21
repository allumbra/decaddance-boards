"""The Decaddance leaderboard alias rule, ported from playfab/cloudscript/decaddance.js
(alias, hashedAlias, showsHandle, googlePlayGamesHandle). The snapshot builder
(snapshot_boards.py) uses it, and test_snapshot_boards.py runs the CloudScript copy
against this one on many players, so the two can never differ.

Privacy by default: the anonymous word-pair alias, unless the player asked to show
their Play Games handle (tag dec_show_handle). Title display names are never shown.
"""
TITLE_ID = "156235"
SHOW_HANDLE_TAG = "dec_show_handle"

# APPEND-ONLY, like the CloudScript lists: a removed or reordered word renames players.
NAME_ADJECTIVES = (
    "Amber", "Arctic", "Azure", "Bold", "Brave", "Breezy", "Bright", "Calm", "Cheerful",
    "Chipper", "Clever", "Cobalt", "Cosmic", "Cozy", "Daring", "Dapper", "Eager", "Emerald",
    "Epic", "Friendly", "Frosty", "Gentle", "Glowing", "Golden", "Happy", "Helpful", "Heroic",
    "Honest", "Hopeful", "Jolly", "Keen", "Kind", "Loyal", "Lucky", "Lunar", "Merry",
    "Mighty", "Misty", "Nimble", "Noble", "Patient", "Peppy", "Plucky", "Polite", "Quiet",
    "Rocky", "Royal", "Shiny", "Silver", "Smiling", "Snowy", "Solar", "Sparkly", "Speedy",
    "Starry", "Steady", "Stellar", "Sturdy", "Sunny", "Super", "Swift", "Tidy", "Trusty",
    "Turbo", "Valiant", "Wise", "Zippy",
)

NAME_NOUNS = (
    "Anvil", "Astronaut", "Badger", "Beacon", "Beetle", "Bison", "Boulder", "Builder",
    "Captain", "Champion", "Chipmunk", "Climber", "Comet", "Cricket", "Crystal", "Diamond",
    "Dolphin", "Dragon", "Dragonfly", "Eagle", "Elephant", "Engineer", "Explorer", "Falcon",
    "Firefly", "Gecko", "Geode", "Giraffe", "Griffin", "Hawk", "Hedgehog", "Heron",
    "Inventor", "Kangaroo", "Koala", "Ladybug", "Lantern", "Lemur", "Lion", "Llama", "Lynx",
    "Magnet", "Meerkat", "Meteor", "Miner", "Mole", "Moose", "Narwhal", "Nugget", "Octopus",
    "Opal", "Orca", "Owl", "Panda", "Parrot", "Pebble", "Pelican", "Penguin", "Phoenix",
    "Pickaxe", "Pilot", "Pioneer", "Planet", "Puffin", "Quartz", "Ranger", "Robin", "Robot",
    "Rocket", "Scout", "Seahorse", "Sparrow", "Squirrel", "Starfish", "Tiger", "Topaz",
    "Toucan", "Turtle", "Unicorn", "Voyager", "Walrus", "Wizard", "Wolf", "Yak", "Zebra",
)

BLOCKED_NUMBERS = ["69", "88", "187", "311", "420", "666", "911", "1312", "1418", "2316", "5318", "7734", "8008"]


# What a JavaScript regex \\s matches (the CloudScript trims with it), so both trim the same.
JS_WHITESPACE = ("\t\n\x0b\x0c\r \xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
                 "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")


def _blocked(number):
    return any(word in str(number) for word in BLOCKED_NUMBERS)


def hashed_alias(row):
    """Stable and stateless: the same PlayFab id always gives the same name."""
    player = row.get("PlayFabId") if isinstance(row, dict) else None
    ident = player if isinstance(player, str) else "anonymous"
    # CloudScript hashes UTF-16 code units; PlayFab ids are ASCII hex.
    units = []
    for ch in ident:
        code = ord(ch)
        if code > 0xFFFF:
            code -= 0x10000
            units.extend((0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
        else:
            units.append(code)
    h = 0
    for u in units:
        h = (h * 31 + u) & 0xFFFFFFFF
    other = 2166136261
    for u in units:
        other = ((other ^ u) * 16777619) & 0xFFFFFFFF
    number = 1000 + other % 9000
    tries = 0
    while tries < 9000 and _blocked(number):
        number = 1000 + (number - 1000 + 1) % 9000
        tries += 1
    adjective = NAME_ADJECTIVES[h % len(NAME_ADJECTIVES)]
    noun = NAME_NOUNS[(h // len(NAME_ADJECTIVES)) % len(NAME_NOUNS)]
    return "%s %s %d" % (adjective, noun, number)


def _profile(row):
    profile = row.get("Profile") if isinstance(row, dict) else None
    return profile if isinstance(profile, dict) else {}


def google_play_games_handle(row):
    linked = _profile(row).get("LinkedAccounts")
    if not isinstance(linked, list):
        return None
    for account in linked:
        if not isinstance(account, dict) or account.get("Platform") != "GooglePlayGames" \
                or not isinstance(account.get("Username"), str):
            continue
        handle = account["Username"].strip(JS_WHITESPACE)
        if 0 < len(handle) <= 80:
            return handle
    return None


def is_show_handle_tag(value):
    return value == SHOW_HANDLE_TAG or value == "title.%s.%s" % (TITLE_ID, SHOW_HANDLE_TAG)


def shows_handle(row):
    tags = _profile(row).get("Tags")
    if not isinstance(tags, list):
        return False
    return any(isinstance(t, dict) and is_show_handle_tag(t.get("TagValue")) for t in tags)


def alias(row):
    handle = google_play_games_handle(row) if shows_handle(row) else None
    return handle or hashed_alias(row)
