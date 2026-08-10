"""Country → company registry reference data.

Keyed on ISO 3166-1 alpha-2 to match `startup_profiles.country`. The mobile
client previously owned an equivalent map keyed on display names (`"Nigeria"`);
that map cannot drive server-side labels, and two copies drift. This is the
one the API returns from `GET /v1/registries`.

**No number format validation.** `number_example` is a placeholder hint for the
form, not a pattern to enforce. A regex that rejects a real founder's real
number would be a false positive on a registration document — the failure mode
consistency checks already refuse to introduce.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Registry:
    """What a jurisdiction calls its company register and its certificate."""

    country: str
    """ISO 3166-1 alpha-2."""

    country_name: str
    registrar: str
    """Full name of the registering body."""

    short_name: str
    """Abbreviation the founder will recognise, e.g. `CAC`."""

    document_name: str
    """What the certificate of incorporation is called locally."""

    number_label: str
    """What the registration number field should be labelled."""

    number_example: str
    """Placeholder hint only — never validated against."""


REGISTRIES: Final[dict[str, Registry]] = {
    "NG": Registry(
        country="NG",
        country_name="Nigeria",
        registrar="Corporate Affairs Commission",
        short_name="CAC",
        document_name="Certificate of Incorporation",
        number_label="RC number",
        number_example="RC 1234567",
    ),
    "GH": Registry(
        country="GH",
        country_name="Ghana",
        registrar="Registrar-General's Department",
        short_name="RGD",
        document_name="Certificate of Incorporation",
        number_label="Company number",
        number_example="CS123456789",
    ),
    "KE": Registry(
        country="KE",
        country_name="Kenya",
        registrar="Business Registration Service",
        short_name="BRS",
        document_name="Certificate of Incorporation",
        number_label="Company number",
        number_example="C.123456",
    ),
    "ZA": Registry(
        country="ZA",
        country_name="South Africa",
        registrar="Companies and Intellectual Property Commission",
        short_name="CIPC",
        document_name="Certificate of Incorporation",
        number_label="Registration number",
        number_example="2020/123456/07",
    ),
    "GB": Registry(
        country="GB",
        country_name="United Kingdom",
        registrar="Companies House",
        short_name="Companies House",
        document_name="Certificate of Incorporation",
        number_label="Company number",
        number_example="12345678",
    ),
    "US": Registry(
        country="US",
        country_name="United States",
        registrar="Secretary of State",
        short_name="Secretary of State",
        document_name="Certificate of Incorporation / Formation",
        number_label="Entity / file number",
        number_example="1234567",
    ),
    "CA": Registry(
        country="CA",
        country_name="Canada",
        registrar="Corporations Canada",
        short_name="Corporations Canada",
        document_name="Certificate of Incorporation",
        number_label="Corporation number",
        number_example="123456-7",
    ),
    "IN": Registry(
        country="IN",
        country_name="India",
        registrar="Ministry of Corporate Affairs",
        short_name="MCA",
        document_name="Certificate of Incorporation",
        number_label="CIN",
        number_example="U72900MH2020PTC123456",
    ),
    "SG": Registry(
        country="SG",
        country_name="Singapore",
        registrar="Accounting and Corporate Regulatory Authority",
        short_name="ACRA",
        document_name="BizFile / Certificate of Incorporation",
        number_label="UEN",
        number_example="202012345A",
    ),
    "DE": Registry(
        country="DE",
        country_name="Germany",
        registrar="Handelsregister",
        short_name="Handelsregister",
        document_name="Handelsregisterauszug",
        number_label="HRB / HRA number",
        number_example="HRB 123456",
    ),
    "NL": Registry(
        country="NL",
        country_name="Netherlands",
        registrar="Kamer van Koophandel",
        short_name="KvK",
        document_name="Extract from the Trade Register",
        number_label="KvK number",
        number_example="12345678",
    ),
}


def registry_for(country: str | None) -> Registry | None:
    """The registry for this ISO country code, or `None` if we have none.

    Unknown and blank countries are a normal case — the form still asks for
    legal name and registration number as free text, and the certificate is
    still accepted as `registration_certificate`. Missing a map entry is not a
    refusal.
    """
    if country is None:
        return None
    return REGISTRIES.get(country.strip().upper())


__all__ = [
    "REGISTRIES",
    "Registry",
    "registry_for",
]
