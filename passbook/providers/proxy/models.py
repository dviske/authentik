"""passbook proxy models"""
import string
from random import SystemRandom
from typing import Iterable, Optional, Type
from urllib.parse import urljoin

from django.db import models
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils.translation import gettext as _

from passbook.crypto.models import CertificateKeyPair
from passbook.lib.models import DomainlessURLValidator
from passbook.outposts.models import OutpostModel
from passbook.providers.oauth2.constants import (
    SCOPE_OPENID,
    SCOPE_OPENID_EMAIL,
    SCOPE_OPENID_PROFILE,
)
from passbook.providers.oauth2.models import (
    ClientTypes,
    JWTAlgorithms,
    OAuth2Provider,
    ResponseTypes,
    ScopeMapping,
)

SCOPE_PB_PROXY = "pb_proxy"


def get_cookie_secret():
    """Generate random 32-character string for cookie-secret"""
    return "".join(
        SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(32)
    )


def _get_callback_url(uri: str) -> str:
    return urljoin(uri, "/pbprox/callback")


class ProxyProvider(OutpostModel, OAuth2Provider):
    """Protect applications that don't support any of the other
    Protocols by using a Reverse-Proxy."""

    internal_host = models.TextField(
        validators=[DomainlessURLValidator(schemes=("http", "https"))]
    )
    external_host = models.TextField(
        validators=[DomainlessURLValidator(schemes=("http", "https"))]
    )
    internal_host_ssl_validation = models.BooleanField(
        default=True,
        help_text=_("Validate SSL Certificates of upstream servers"),
        verbose_name=_("Internal host SSL Validation"),
    )

    skip_path_regex = models.TextField(
        default="",
        blank=True,
        help_text=_(
            (
                "Regular expressions for which authentication is not required. "
                "Each new line is interpreted as a new Regular Expression."
            )
        ),
    )

    basic_auth_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Set HTTP-Basic Authentication"),
        help_text=_(
            "Set a custom HTTP-Basic Authentication header based on values from passbook."
        ),
    )
    basic_auth_user_attribute = models.TextField(
        blank=True,
        verbose_name=_("HTTP-Basic Username"),
        help_text=_(
            (
                "User Attribute used for the user part of the HTTP-Basic Header. "
                "If not set, the user's Email address is used."
            )
        ),
    )
    basic_auth_password_attribute = models.TextField(
        blank=True,
        verbose_name=_("HTTP-Basic Password"),
        help_text=_(
            ("User Attribute used for the password part of the HTTP-Basic Header.")
        ),
    )

    certificate = models.ForeignKey(
        CertificateKeyPair, on_delete=models.SET_NULL, null=True, blank=True,
    )

    cookie_secret = models.TextField(default=get_cookie_secret)

    @property
    def form(self) -> Type[ModelForm]:
        from passbook.providers.proxy.forms import ProxyProviderForm

        return ProxyProviderForm

    @property
    def launch_url(self) -> Optional[str]:
        """Use external_host as launch URL"""
        return self.external_host

    def html_setup_urls(self, request: HttpRequest) -> Optional[str]:
        """Overwrite Setup URLs as they are not needed for proxy"""
        return None

    def set_oauth_defaults(self):
        """Ensure all OAuth2-related settings are correct"""
        self.client_type = ClientTypes.CONFIDENTIAL
        self.response_type = ResponseTypes.CODE
        self.jwt_alg = JWTAlgorithms.RS256
        self.rsa_key = CertificateKeyPair.objects.first()
        scopes = ScopeMapping.objects.filter(
            scope_name__in=[
                SCOPE_OPENID,
                SCOPE_OPENID_PROFILE,
                SCOPE_OPENID_EMAIL,
                SCOPE_PB_PROXY,
            ]
        )
        self.property_mappings.set(scopes)
        self.redirect_uris = "\n".join(
            [
                _get_callback_url(self.external_host),
                _get_callback_url(self.internal_host),
            ]
        )

    def __str__(self):
        return f"Proxy Provider {self.name}"

    def get_required_objects(self) -> Iterable[models.Model]:
        required_models = [self]
        if self.certificate is not None:
            required_models.append(self.certificate)
        return required_models

    class Meta:

        verbose_name = _("Proxy Provider")
        verbose_name_plural = _("Proxy Providers")
