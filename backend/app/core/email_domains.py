"""Company email domains: recognising them, and reading a company name off one.

Founders register with a company address (`DECISIONS.md` **D20**, `AUTH.md`
section 3.4), and the domain they verify is then the source of the initial
company name on their Startup Profile.

Lives in `core` rather than in a module because two modules need it and they may
not reach into each other's internals (`ARCHITECTURE.md` section 3): `identity`
enforces the registration rule, `intake` derives the profile name. Everything
here is a pure function over a string -- the *decision* to refuse a signup
stays in `identity.service`, where the rest of the registration policy lives.

**The blocklist is a heuristic, not a security control.** It recognises the
consumer mailbox providers people actually use; it cannot enumerate every one,
and passing it proves nothing about corporate identity -- anyone can buy a
domain for a few pounds. Treat "has a company domain" as a signal of intent,
never as verification that a company exists or that this person belongs to it.
What *is* verified is that the person controls the address, because an account
stays `pending_verification` until they click the emailed link (T1.2b).
"""

from typing import Final

# Consumer mailbox providers. Deliberately a literal set rather than a fetched
# list: a network call on the registration path would be a new failure mode on
# the one endpoint that must not wobble, and this list changes about as often as
# the providers themselves do.
CONSUMER_EMAIL_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        # Google
        "gmail.com",
        "googlemail.com",
        # Microsoft
        "outlook.com",
        "hotmail.com",
        "hotmail.co.uk",
        "live.com",
        "live.co.uk",
        "msn.com",
        # Yahoo
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.co.in",
        "ymail.com",
        "rocketmail.com",
        # Apple
        "icloud.com",
        "me.com",
        "mac.com",
        # Privacy-focused
        "proton.me",
        "protonmail.com",
        "pm.me",
        "tutanota.com",
        "tuta.io",
        # Other mainstream
        "aol.com",
        "gmx.com",
        "gmx.net",
        "mail.com",
        "mail.ru",
        "yandex.com",
        "yandex.ru",
        "zoho.com",
        "fastmail.com",
        "hushmail.com",
        "inbox.com",
        # Common in the platform's launch markets (PRD: NG, UAE, UK, US)
        "yahoo.co.za",
        "rediffmail.com",
    }
)

# Second-level labels that are part of a public suffix rather than a company
# name: `acme.co.uk` is Acme, not "Co". Small and explicit because the correct
# general solution is the Public Suffix List, which means a new dependency
# (`tldextract`) for a handful of cases (`CLAUDE.md` section 2 -- stay cheap).
# `com.ng` and `co.za` matter here: the PRD's launch markets include Nigeria.
_PUBLIC_SECOND_LEVEL: Final[frozenset[str]] = frozenset(
    {"co", "com", "net", "org", "ac", "gov", "edu", "or", "ne", "gob"}
)


def email_domain(email: str) -> str | None:
    """The domain part of an address, lowercased.

    `None` when there is no single `@` with something on each side. The caller
    has usually validated the address already; this stays defensive because it
    is reached from two modules and a `None` is easier to handle correctly than
    an `IndexError`.
    """
    local, separator, domain = email.strip().lower().rpartition("@")
    if not separator or not local or not domain:
        return None
    return domain


def is_consumer_domain(email: str) -> bool:
    """Whether this address belongs to a consumer mailbox provider.

    Matches the domain and also its registrable form, so `@mail.gmail.com`
    cannot walk around a `gmail.com` entry. An unparseable address is not
    reported as consumer -- it fails address validation first, and answering
    "yes" here would attribute the wrong reason to the rejection.
    """
    domain = email_domain(email)
    if domain is None:
        return False
    if domain in CONSUMER_EMAIL_DOMAINS:
        return True
    labels = domain.split(".")
    for start in range(1, len(labels) - 1):
        if ".".join(labels[start:]) in CONSUMER_EMAIL_DOMAINS:
            return True
    return False


def company_name_from_email(email: str) -> str | None:
    """A first guess at the company name behind a company address.

    `founder@acme.com` and `founder@mail.acme.co.uk` both give "Acme". The rule
    is: drop the public suffix, take the last label that remains, turn
    separators into spaces, and title-case it.

    **This is a prefill, not a fact.** `getacme.io` becomes "Getacme" and
    `acme-group.com` becomes "Acme Group"; both are close enough to save typing
    and wrong often enough that the founder must be able to correct it. Nothing
    downstream should treat the result as the company's legal name.

    Returns `None` when nothing usable can be read out, including for consumer
    domains -- "Gmail" is never the answer to what a company is called.
    """
    domain = email_domain(email)
    if domain is None or is_consumer_domain(email):
        return None

    labels = [label for label in domain.split(".") if label]
    if len(labels) < 2:
        return None

    labels.pop()  # the TLD: .com, .uk, .ng
    if len(labels) > 1 and labels[-1] in _PUBLIC_SECOND_LEVEL:
        labels.pop()  # .co.uk, .com.ng

    name = labels[-1].replace("-", " ").replace("_", " ").strip()
    if not name:
        return None
    return " ".join(word.capitalize() for word in name.split())


__all__ = [
    "CONSUMER_EMAIL_DOMAINS",
    "company_name_from_email",
    "email_domain",
    "is_consumer_domain",
]
