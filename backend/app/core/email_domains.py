"""Company email domains: recognising them, and reading a company name off one.

Founders register with a company address (`DECISIONS.md` **D20**, `AUTH.md`
section 3.4), and the domain they verify is then the source of the initial
company name on their Startup Profile.

Lives in `core` rather than in a module because two modules need it and they may
not reach into each other's internals (`ARCHITECTURE.md` section 3): `identity`
enforces the registration rule, `intake` derives the profile name. Everything
here is a pure function over a string -- the *decision* to refuse a signup
stays in `identity.service`, where the rest of the registration policy lives.

**Two lists, two different rules.** `CONSUMER_EMAIL_DOMAINS` is an identity
signal and applies to founders only (D20 exempts investors: an angel investing
personally has no company domain). `DISPOSABLE_EMAIL_DOMAINS` is an account-
takeover control and applies to everyone -- see its own comment for why a
publicly-readable inbox is a different problem from a personal one.

**Neither list verifies a company.** They recognise the providers people
actually use; they cannot enumerate every one, and passing them proves nothing
about corporate identity -- anyone can buy a domain for a few pounds. Treat "has
a company domain" as a signal of intent, never as verification that a company
exists or that this person belongs to it.

What *is* verified is that the person controls the address: an account stays
`pending_verification` until they click the emailed link (T1.2b). That is also
why there is no MX lookup here. It would prove the domain can receive mail, but
the verification email already proves it *did* -- and a DNS call on the
registration path buys a new failure mode on an endpoint that must not wobble,
for a check the next step performs anyway.
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

# Throwaway inbox services. A separate list from the consumer providers above
# because the rule that uses it is different in kind, and stricter.
#
# **These are not merely "not a company" -- most of them are publicly readable.**
# A mailinator or yopmail inbox has no password: anyone who knows the address
# can open it. So an account registered on one hands its verification link, and
# every future password-reset link, to whoever cares to look. That is account
# takeover by design, not a weak identity signal, and it is why this list is
# enforced for **every** self-service role while `CONSUMER_EMAIL_DOMAINS` is
# founders-only -- an investor reading summary-tier startup data through a
# public mailbox is the same breach as a founder doing it.
#
# Same literal-set tradeoff as above, and the same caveat: it cannot be
# exhaustive. New throwaway domains appear constantly and a determined person
# will find one. It removes the effortless path, which is what a heuristic at
# this layer can honestly do.
DISPOSABLE_EMAIL_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        # Public-inbox services: no password, readable by anyone
        "mailinator.com",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
        "dispostable.com",
        "mailnesia.com",
        "moakt.com",
        # Timed self-destructing inboxes
        "10minutemail.com",
        "10minutemail.net",
        "20minutemail.com",
        "tempmail.com",
        "temp-mail.org",
        "temp-mail.io",
        "tempmailo.com",
        "minutemail.com",
        "throwawaymail.com",
        # Guerrilla Mail and its rotating aliases
        "guerrillamail.com",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamail.biz",
        "guerrillamail.de",
        "sharklasers.com",
        "grr.la",
        "spam4.me",
        # Other well-known throwaways
        "trashmail.com",
        "trashmail.de",
        "getnada.com",
        "nada.email",
        "maildrop.cc",
        "mailcatch.com",
        "fakeinbox.com",
        "spamgourmet.com",
        "mytemp.email",
        "emailondeck.com",
        "burnermail.io",
        "mohmal.com",
        "tempr.email",
        "discard.email",
        "einrot.com",
        "fakemail.net",
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


def is_disposable_domain(email: str) -> bool:
    """Whether this address is a throwaway inbox.

    Subdomain matching works the same way as `is_consumer_domain`, which matters
    more here: Guerrilla Mail hands out addresses on rotating subdomains, so
    matching only the exact domain would miss most of what it issues.

    Kept separate from `is_consumer_domain` rather than folded into one
    `is_refused_domain` helper, because the two answer different questions and
    the caller applies them to different roles. Merging them would make it
    impossible to tell a founder "use your company address" without also telling
    an investor the same thing, which is not the rule (D20).
    """
    domain = email_domain(email)
    if domain is None:
        return False
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return True
    labels = domain.split(".")
    return any(
        ".".join(labels[start:]) in DISPOSABLE_EMAIL_DOMAINS
        for start in range(1, len(labels) - 1)
    )


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
    and throwaway domains -- neither "Gmail" nor "Mailinator" is ever the answer
    to what a company is called. Registration refuses both before a profile can
    exist, so this is belt and braces; it is here because this function is also
    reachable from `intake` and a prefilled "Temp Mail" would be worse than a
    blank field.
    """
    domain = email_domain(email)
    if domain is None or is_consumer_domain(email) or is_disposable_domain(email):
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
    "DISPOSABLE_EMAIL_DOMAINS",
    "company_name_from_email",
    "email_domain",
    "is_consumer_domain",
    "is_disposable_domain",
]
