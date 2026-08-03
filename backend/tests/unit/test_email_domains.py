"""Recognising company domains and reading a company name off one.

Pure string functions behind two rules that face users directly: a founder is
refused registration on a consumer address (`DECISIONS.md` D20), and the domain
they do use becomes the first company name on their profile. Both are visible
enough that the edge cases are worth pinning down here rather than discovering
them in support tickets.
"""

import pytest

from app.core.email_domains import (
    CONSUMER_EMAIL_DOMAINS,
    DISPOSABLE_EMAIL_DOMAINS,
    company_name_from_email,
    email_domain,
    is_consumer_domain,
    is_disposable_domain,
)


class TestEmailDomain:
    @pytest.mark.parametrize(
        ("address", "expected"),
        [
            ("founder@acme.com", "acme.com"),
            ("Founder@ACME.com", "acme.com"),
            ("  founder@acme.com  ", "acme.com"),
            ("first.last+tag@acme.co.uk", "acme.co.uk"),
        ],
    )
    def test_extracts_and_normalises(self, address: str, expected: str) -> None:
        assert email_domain(address) == expected

    @pytest.mark.parametrize(
        "address", ["", "no-at-sign", "@acme.com", "founder@", "   "]
    )
    def test_unparseable_gives_none(self, address: str) -> None:
        assert email_domain(address) is None


class TestDisposableDomains:
    """Throwaway inboxes, which is a takeover problem rather than an identity one.

    Every address below passed founder registration before these existed, and
    several of them -- mailinator, yopmail, dispostable -- serve inboxes with no
    password at all. An account on one publishes its own verification link and
    every future password-reset link to anybody who knows the address.
    """

    @pytest.mark.parametrize(
        "address",
        [
            "founder@mailinator.com",
            "founder@MAILINATOR.COM",
            "founder@yopmail.com",
            "founder@10minutemail.com",
            "founder@guerrillamail.com",
            "founder@sharklasers.com",
            "founder@temp-mail.org",
            "founder@trashmail.com",
            "founder@getnada.com",
            "founder@dispostable.com",
            "founder@maildrop.cc",
        ],
    )
    def test_throwaway_providers_are_recognised(self, address: str) -> None:
        assert is_disposable_domain(address)

    @pytest.mark.parametrize(
        "address",
        [
            "founder@acme.com",
            "founder@kanmi.com.ng",
            "founder@gmail.com",
            "founder@example.test",
        ],
    )
    def test_real_and_consumer_domains_are_not_disposable(self, address: str) -> None:
        """Consumer is a different rule: different message, different scope."""
        assert not is_disposable_domain(address)

    def test_a_rotating_subdomain_does_not_slip_through(self) -> None:
        """Guerrilla Mail issues addresses on subdomains; exact matching misses them."""
        assert is_disposable_domain("founder@inbox.guerrillamail.com")

    def test_a_lookalike_domain_is_not_matched(self) -> None:
        assert not is_disposable_domain("founder@notmailinator.com")

    def test_unparseable_is_not_reported_as_disposable(self) -> None:
        assert not is_disposable_domain("no-at-sign")

    def test_a_throwaway_never_becomes_a_company_name(self) -> None:
        """ "Temp Mail" as a startup name is worse than a blank field."""
        for address in ("founder@mailinator.com", "founder@temp-mail.org"):
            assert company_name_from_email(address) is None

    def test_the_two_lists_are_disjoint(self) -> None:
        """A domain in both would get whichever message the checks happen to reach.

        The two rules differ in scope and in what they tell the user -- one says
        "use your company address" and applies to founders, the other says "use
        an address you control privately" and applies to everyone. Overlap would
        make which one fires an accident of ordering in `register_user`.
        """
        overlap = CONSUMER_EMAIL_DOMAINS & DISPOSABLE_EMAIL_DOMAINS

        assert not overlap, f"a domain cannot be both: {sorted(overlap)}"


class TestConsumerDomains:
    @pytest.mark.parametrize(
        "address",
        [
            "founder@gmail.com",
            "founder@GMAIL.COM",
            "founder@yahoo.co.uk",
            "founder@outlook.com",
            "founder@hotmail.com",
            "founder@icloud.com",
            "founder@proton.me",
            "founder@yandex.ru",
        ],
    )
    def test_consumer_providers_are_recognised(self, address: str) -> None:
        assert is_consumer_domain(address)

    @pytest.mark.parametrize(
        "address",
        [
            "founder@acme.com",
            "founder@acme.co.uk",
            "founder@kanmi.com.ng",
            "founder@example.test",
            "founder@gmail.acme.com",
        ],
    )
    def test_company_domains_are_not(self, address: str) -> None:
        assert not is_consumer_domain(address)

    def test_a_subdomain_of_a_consumer_provider_does_not_slip_through(self) -> None:
        """`@mail.gmail.com` must not walk around a `gmail.com` entry."""
        assert is_consumer_domain("founder@mail.gmail.com")

    def test_a_lookalike_domain_is_not_matched(self) -> None:
        """Suffix matching is per label -- `notgmail.com` is its own domain."""
        assert not is_consumer_domain("founder@notgmail.com")

    def test_unparseable_is_not_reported_as_consumer(self) -> None:
        """It fails address validation first; the reason must not be wrong."""
        assert not is_consumer_domain("nonsense")

    def test_the_list_is_lowercase(self) -> None:
        """Matching normalises to lowercase, so an entry in caps would be dead."""
        assert all(entry == entry.lower() for entry in CONSUMER_EMAIL_DOMAINS)


class TestCompanyNameFromEmail:
    @pytest.mark.parametrize(
        ("address", "expected"),
        [
            ("founder@acme.com", "Acme"),
            ("founder@ACME.com", "Acme"),
            # Public suffixes are dropped, not turned into the company name.
            ("founder@acme.co.uk", "Acme"),
            ("founder@kanmi.com.ng", "Kanmi"),
            ("founder@acme.co.za", "Acme"),
            # A mail subdomain is not the company.
            ("founder@mail.acme.com", "Acme"),
            ("founder@mail.acme.co.uk", "Acme"),
            # Separators become spaces.
            ("founder@acme-group.com", "Acme Group"),
            ("founder@acme_group.com", "Acme Group"),
        ],
    )
    def test_reads_the_company_label(self, address: str, expected: str) -> None:
        assert company_name_from_email(address) == expected

    @pytest.mark.parametrize(
        "address",
        ["founder@gmail.com", "founder@yahoo.co.uk", "nonsense", "founder@localhost"],
    )
    def test_nothing_usable_gives_none(self, address: str) -> None:
        """An empty name is honest. A wrong one reads as confirmed."""
        assert company_name_from_email(address) is None

    def test_it_is_a_guess_and_the_docstring_says_so(self) -> None:
        """`getacme.io` is not "Acme". Pinned so nobody treats it as a fact."""
        assert company_name_from_email("founder@getacme.io") == "Getacme"
