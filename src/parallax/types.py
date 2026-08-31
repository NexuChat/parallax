"""Core data model.

A *witness* is not a role — it is one point in a matrix of contexts. The app is
expected to behave identically across some axes (a member should reach the same
things in Arabic as in English) and differently across others (an owner should
reach more than a guest). Every finding here is a violation of one of those two
expectations, so the axis a witness varies is what gives its testimony meaning.

Contexts are derived from a baseline by changing exactly ONE axis. That keeps the
run to a handful of witnesses instead of the full cross-product, and — more
importantly — makes every finding causally attributable: if only the viewport
changed, the viewport is why it broke.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------
# Axes
# --------------------------------------------------------------------------

class Privilege(str, Enum):
    """The one axis where witnesses are *expected* to diverge."""

    ANON = "anon"
    MEMBER = "member"
    OWNER = "owner"

    @property
    def rank(self) -> int:
        return {"anon": 0, "member": 1, "owner": 2}[self.value]


@dataclass(frozen=True)
class Role:
    """A privilege level beyond the built-in three.

    Applications rarely stop at anonymous, member and owner. A chat product has
    guests, ranks, room owners and site owners, and "can the room owner do what
    the site owner can" is exactly the question the privilege axis exists for —
    it was simply unaskable while the axis was an enum of three.

    `rank` is supplied by the caller because only the caller knows the ordering.
    Parallax uses it for one decision: a surface reached by a lower rank that a
    higher rank was denied is an inversion, and one reached by a lower rank that
    the baseline was offered is an escalation. Both need an order, and neither
    needs to know what the roles mean.
    """

    value: str
    rank: int

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("a role needs a name")
        if self.rank < 0:
            raise ValueError(f"role {self.value!r} needs a non-negative rank")

    def __str__(self) -> str:
        return self.value


# Either kind of role can sit on a Context: the built-in enum carries its own
# rank, and a declared Role carries the one its caller gave it.
AnyRole = Privilege | Role


class Locale(str, Enum):
    EN = "en"
    AR = "ar"

    @property
    def direction(self) -> str:
        return "rtl" if self is Locale.AR else "ltr"


# Languages written right-to-left, by primary subtag. Direction is derived
# rather than declared because it is a property of the language, not of the
# project — asking someone to state that Hebrew runs right-to-left is asking
# them to get it wrong once.
_RTL_LANGS = frozenset({"ar", "he", "fa", "ur", "ps", "sd", "ug", "dv", "ckb", "yi"})


@dataclass(frozen=True)
class LocaleSpec:
    """A locale beyond the built-in pair.

    The locale axis was an enum of two, which made "does the French rendering
    disagree with the English one" unaskable for the same reason privilege
    questions were once unaskable beyond three roles. A declared locale is any
    BCP 47 tag; its text direction is derived from the language subtag, so a
    declared `he` witness is judged with the same RTL mirror checks as the
    built-in Arabic one.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("a locale needs a language tag")

    @property
    def direction(self) -> str:
        return "rtl" if self.value.split("-")[0].lower() in _RTL_LANGS else "ltr"

    def __str__(self) -> str:
        return self.value


# Either kind of locale can sit on a Context, exactly as with roles.
AnyLocale = Locale | LocaleSpec


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int


MOBILE = Viewport("mobile", 360, 740)
TABLET = Viewport("tablet", 768, 1024)
DESKTOP = Viewport("desktop", 1440, 900)


class Axis(str, Enum):
    """Which dimension a witness varies from the baseline."""

    BASELINE = "baseline"
    PRIVILEGE = "privilege"
    LOCALE = "locale"
    THEME = "theme"
    VIEWPORT = "viewport"
    RELATIONAL = "relational"   # not a derivation: two witnesses acting on each other

    @property
    def expects_equivalence(self) -> bool:
        """True when changing this axis must NOT change what a user can reach.

        Privilege is the sole exception: it is *supposed* to change access, so
        for privilege we hunt sameness, and everywhere else we hunt difference.
        """
        return self is not Axis.PRIVILEGE


@dataclass(frozen=True)
class AxisApplicability:
    """Whether the application claims an axis and why the run did or did not exercise it."""

    axis: Axis
    applicable: bool
    reason: str


@dataclass(frozen=True)
class Context:
    """One witness's full configuration."""

    privilege: AnyRole = Privilege.OWNER
    locale: AnyLocale = Locale.EN
    theme: Theme = Theme.LIGHT
    viewport: Viewport = DESKTOP
    varies: Axis = Axis.BASELINE

    @property
    def name(self) -> str:
        return f"{self.privilege.value}-{self.locale.value}-{self.theme.value}-{self.viewport.name}"

    @property
    def direction(self) -> str:
        return self.locale.direction

    def describe(self) -> str:
        if self.varies is Axis.BASELINE:
            return f"baseline ({self.name})"
        return f"{self.name} (varies: {self.varies.value})"


BASELINE = Context()


def derive_witnesses(
    baseline: Context = BASELINE,
    *,
    extra_roles: Sequence["Role"] = (),
    locales: Sequence[AnyLocale] | None = None,
    viewports: Sequence[Viewport] | None = None,
) -> list[Context]:
    """One-axis-at-a-time derivation: witnesses, never a cross-product.

    Each returned context differs from the baseline in exactly one axis, so any
    disagreement it reports has exactly one candidate cause. The *values* on an
    axis are declarable — which locales, which viewports, which roles — but the
    derivation rule is not: every declared value adds one witness, and the cell
    count grows linearly with the declaration, not multiplicatively.

    `None` means the built-in default for that axis; an explicit empty sequence
    means the caller has decided the axis has nothing to compare, which is a
    statement, not an omission.
    """
    witnesses = [baseline]
    for privilege in (Privilege.MEMBER, Privilege.ANON):
        witnesses.append(replace(baseline, privilege=privilege, varies=Axis.PRIVILEGE))
    # Declared roles are witnesses on the same axis as the built-in three. They
    # are appended rather than substituted, so a run that adds a role does not
    # stop asking the questions it asked before.
    for role in extra_roles:
        witnesses.append(replace(baseline, privilege=role, varies=Axis.PRIVILEGE))
    for locale in (locales if locales is not None else (Locale.AR,)):
        witnesses.append(replace(baseline, locale=locale, varies=Axis.LOCALE))
    witnesses.append(replace(baseline, theme=Theme.DARK, varies=Axis.THEME))
    for viewport in (viewports if viewports is not None else (MOBILE, TABLET)):
        witnesses.append(replace(baseline, viewport=viewport, varies=Axis.VIEWPORT))
    return witnesses


# --------------------------------------------------------------------------
# Surfaces and testimony
# --------------------------------------------------------------------------

class SurfaceKind(str, Enum):
    ROUTE = "route"              # a URL the app renders
    AFFORDANCE = "affordance"    # a control on a route (button, link, menu item)


@dataclass(frozen=True)
class Surface:
    """Something a witness can attempt. Discovered by the baseline, replayed by all."""

    kind: SurfaceKind
    path: str
    selector: str | None = None
    label: str | None = None

    @property
    def id(self) -> str:
        raw = f"{self.kind.value}|{self.path}|{self.selector or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def describe(self) -> str:
        if self.kind is SurfaceKind.ROUTE:
            return self.path
        return f"{self.label or self.selector} on {self.path}"


class Outcome(str, Enum):
    REACHED = "reached"    # rendered, and the surface was available
    BLOCKED = "blocked"    # denied: redirected to login, 403, or affordance absent
    PARTIAL = "partial"    # rendered but degraded — empty state, error, broken layout
    ERROR = "error"        # the witness itself failed; never counted as evidence


class Defect(str, Enum):
    """Render-level problems a witness can observe on its own, without comparison.

    These are the axis-specific invariants: they need no second witness, but the
    differ still reports which axis was varied so the cause is unambiguous.
    """

    HORIZONTAL_OVERFLOW = "horizontal_overflow"   # content wider than the viewport
    RTL_NOT_MIRRORED = "rtl_not_mirrored"         # layout stayed LTR under an RTL locale
    THEME_LAYOUT_SHIFT = "theme_layout_shift"     # dark mode recoloured *and* moved something
    UNTRANSLATED = "untranslated"                 # raw i18n keys or wrong-language text
    LOW_CONTRAST = "low_contrast"                 # fails WCAG AA in this theme
    CLIPPED = "clipped"                           # text or control cut off
    OFFSCREEN_CONTROL = "offscreen_control"       # actionable element unreachable
    SMALL_TAP_TARGET = "small_tap_target"         # below the 44px WCAG 2.2 minimum


@dataclass(frozen=True)
class DefectObservation:
    """One probe measurement tied to the element it observed."""

    defect: Defect
    selector: str | None = None
    detail: str = ""


@dataclass
class Testimony:
    """One witness's account of one surface. Evidence, immutable once written."""

    surface: Surface
    context: Context
    outcome: Outcome
    http_status: int | None = None
    final_path: str | None = None      # redirects are how denials usually announce themselves
    content_signature: str | None = None  # hash of visible text/structure, for parity checks
    layout_signature: str | None = None   # hash of geometry alone: must not move on the theme axis
    geometry: list[dict[str, Any]] = field(default_factory=list)  # landmark boxes, for the mirror test
    document_lang: str | None = None
    support: dict[str, bool] = field(default_factory=dict)
    defects: list[Defect] = field(default_factory=list)
    observations: list[DefectObservation] = field(default_factory=list)
    note: str = ""
    screenshot: str | None = None      # object path, never bytes
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_evidence(self) -> bool:
        """A failed or 5xx witness proves no application state or policy."""
        return self.outcome is not Outcome.ERROR and not (
            self.http_status is not None and 500 <= self.http_status < 600
        )

    @property
    def reached(self) -> bool:
        return self.is_evidence and self.outcome in (Outcome.REACHED, Outcome.PARTIAL)


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

class FindingKind(str, Enum):
    ESCALATION = "escalation"          # privilege axis: sameness where difference was required
    POLICY_INVERSION = "inversion"     # privilege axis: the higher role is denied, the lower allowed
    CAPABILITY_DRIFT = "drift"         # equivalence axis: access changed when it must not have
    RENDER_DEFECT = "render"           # axis-specific invariant broken (RTL, overflow, contrast…)
    CONTENT_DIVERGENCE = "divergence"  # same surface, materially different content across an equivalence axis
    PROPAGATION_FAILURE = "propagation"  # the sender acted and the receiver never saw it
    REVOCATION_LAG = "revocation"        # an already-open session retained authority after revocation
    DEAD_SURFACE = "dead"              # nobody could reach it


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True)
class FormAction:
    """The replayable subset of a relational sender action.

    `kind` distinguishes a form submission from a plain click. Without it a
    click replayed as a submission calls requestSubmit() on a button, which
    throws — a generated spec that fails for a reason that has nothing to do
    with the finding it was written to prove.
    """

    form: str
    checks: tuple[str, ...] = ()
    fills: tuple[tuple[str, str], ...] = ()
    kind: str = "submit_form"


@dataclass(frozen=True)
class EffectExpectation:
    """A replayable receiver predicate from the safe scenario vocabulary."""

    kind: str
    selector: str | None = None
    url: str | None = None
    items: str | None = None
    field: str | None = None
    equals: str | None = None


@dataclass(frozen=True)
class RelationalReplay:
    """Enough normalized data to turn a measured relation into a CI test."""

    sender: Privilege
    receiver: Privilege
    action: FormAction
    effect: EffectExpectation
    deadline_ms: int
    max_lag_ms: int | None = None


class RevocationPlane(str, Enum):
    DECISION = "decision"
    DISTRIBUTION = "distribution"
    ENFORCEMENT = "enforcement"
    EFFECTS = "effects"


@dataclass(frozen=True)
class RevocationPlanes:
    """The four independently observable parts of a revocation."""

    decision: bool | None
    distribution: bool | None
    enforcement: bool | None
    effects: bool | None

    @property
    def passed(self) -> tuple[RevocationPlane, ...]:
        return tuple(
            plane for plane in RevocationPlane
            if getattr(self, plane.value) is True
        )

    @property
    def failed(self) -> tuple[RevocationPlane, ...]:
        return tuple(
            plane for plane in RevocationPlane
            if getattr(self, plane.value) is False
        )

    @property
    def unmeasured(self) -> tuple[RevocationPlane, ...]:
        return tuple(
            plane for plane in RevocationPlane
            if getattr(self, plane.value) is None
        )


@dataclass(frozen=True)
class RevocationLag:
    """Measured authority persistence for a session that stayed open."""

    lag_ms: int | None
    deadline_ms: int
    max_lag_ms: int
    probes: tuple[str, ...]
    planes: RevocationPlanes
    effect_selector: str | None = None
    setup_error: str | None = None
    measurement_error: str | None = None

    @property
    def display_lag(self) -> str:
        if self.setup_error or self.measurement_error:
            return "unmeasured"
        return f"{self.lag_ms}ms" if self.lag_ms is not None else f">= {self.deadline_ms}ms"


@dataclass
class Finding:
    kind: FindingKind
    severity: Severity
    surface: Surface
    axis: Axis
    summary: str
    testimonies: list[Testimony]   # the exact evidence this rests on
    revocation: RevocationLag | None = None
    replay: RelationalReplay | None = None
    defect: Defect | None = None
    evidence: str | None = None
    # What distinguishes two findings that share a surface, kind and axis.
    label: str | None = None

    @property
    def id(self) -> str:
        identity = f"{self.kind.value}-{self.axis.value}-{self.surface.id}"
        if self.kind is FindingKind.RENDER_DEFECT and self.defect is not None:
            return f"{identity}-{self.defect.value}"
        # Two scenarios can end on the same surface with the same kind and axis —
        # "delete user" and "change billing" both escalating on /admin — and the
        # run-level deduplicator drops the second without a feed event, so the
        # report understates the exposure. The label distinguishes them, and a
        # finding without one keeps the identity it always had.
        if self.label:
            digest = hashlib.blake2s(self.label.encode("utf-8"), digest_size=4).hexdigest()
            return f"{identity}-{digest}"
        return identity

    def evidence_line(self) -> str:
        parts = [f"{t.context.name}={t.outcome.value}" for t in self.testimonies]
        if self.evidence:
            parts.append(self.evidence)
        return " · ".join(parts)
