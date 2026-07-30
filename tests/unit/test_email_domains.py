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
    company_name_from_email,
    email_domain,
    is_consumer_domain,
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
