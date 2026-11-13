"""Backward-compatible import path (v2 kept every adapter in this module)."""

from . import ADAPTERS, adapter_for, board_from_url  # noqa: F401
from .amazon import AmazonJobsAdapter  # noqa: F401
from .corporate import AccentureAdapter, CapgeminiAdapter, TcsIbeginAdapter  # noqa: F401
from .html_pages import GenericHtmlAdapter, PaginatedHtmlAdapter  # noqa: F401
from .public_ats import AshbyAdapter, GreenhouseAdapter, LeverAdapter, SmartRecruitersAdapter  # noqa: F401
from .successfactors import SuccessFactorsAdapter  # noqa: F401
from .workday import WorkdayAdapter  # noqa: F401
