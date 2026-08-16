# gwsproto sema lay-over — can every word share an identity base?

Status: Draft · Pass 0 · Updated 2026-08-15

> What this is: the experiment behind adding `GwsprotoSemaType`, a shared
> base giving every gwsproto sema word `type_name_value()` /
> `version_value()`. Code under test: `gridworks-scada` `jm/spruce-unlimbo`
> working tree (HEAD `488b9439` + the HydronicLayout collapse cluster).
> Reproducer: `run.py` (exit 0 = every check passed).

## Why

`HydronicLayout` is being sema-fied to hold its layout word rather than a
dict, which needs the word's TypeName. Reading it off a hand-rolled helper
per call site is the wrong shape: type-name access belongs to every sema
word, as it already does in sema's own runtime (`SemaType`,
`sema/src/sema/runtime/base.py:72`) and in gwbase's vendored copy of it
(`GwBaseSemaType`). gwsproto is the outlier, carrying only a free function
(`type_helpers/type_name_literal.py`).

The obvious move — adopt sema's `SemaType` — is blocked, and the reason is
worth stating because it is invisible from the outside.

## The constraint

gwproto discovers payload types in `gwproto/decoders.py:148-171`
(`get_candidate_payload_classes`). A class joins the discriminated union
only if it declares a field **literally named** `TypeName` whose annotation
is a `Literal` with a non-empty default. `model_fields` is keyed by field
name, never by alias. That predicate feeds both decode paths:
`create_message_model` (`decoders.py:218`, the MQTT union built at
`actors/codec_factories.py:35`) and `UnionWrapper.create` (`:253`, behind
gwsproto's own `ComponentDecoder` / `DeviceTypeDecoder`).

Sema's `SemaType` declares snake `type_name` with a `snake_to_pascal`
alias. Such a class serializes to a perfectly conformant payload —
`{"TypeName": "...", "Version": "000"}`, which `sema validate` passes with
exit 0 — while gwproto discovers it as `[]`. The union is then built
silently missing those types. **`sema validate` cannot catch this**: it
checks the wire payload against the schema, and the field name never
reaches the wire. A generated-from-snapshot gwsproto is blocked on exactly
this, not on anything about the schemas themselves.

A second hazard sits behind it: pydantic **merges** a base's
`model_config` into every subclass, even one declaring its own. A base
carrying `frozen=True, extra="forbid"` (as `SemaType` does) would silently
freeze all 145 words and forbid extras where words deliberately allow them.

## The shape tested

Fieldless and config-less; method surface only.

```python
class GwsprotoSemaType(BaseModel):
    @classmethod
    def type_name_value(cls) -> str: ...   # model_fields["TypeName"].default
    @classmethod
    def version_value(cls) -> str | None: ...
```

Carrying no `TypeName` field is what makes the base itself invisible to
discovery; carrying no `model_config` is what keeps 145 words unchanged.
Inheriting no fields is also why the `GridWorks_CLAUDE.md` FLAT note does
not bite — this is not a schema hierarchy, it is an accessor.

## Setup

`run.py` copies the whole `gwsproto` package to a scratch dir, injects the
base, and rewrites every word to inherit it:

- 137 `class X(BaseModel)` → `class X(GwsprotoSemaType)` across 126 files
- `ComponentBase(BaseModel)` → `(GwsprotoSemaType)`, reaching its 19
  component subclasses through `DeviceComponentBase` /
  `BoardResidentComponentBase`
- the 2 words on gwproto's external `EventBase` (`RemainingElecEvent`,
  `ReportEvent`) take the lay-over as a **second** base — we do not own
  `EventBase`, so it cannot be re-parented. MRO resolves
  `ReportEvent → EventBase → GwsprotoSemaType → BaseModel`.

It then probes baseline and patched packages in separate interpreters and
compares. Nothing in the repo working tree is touched.

## Found — PASS (2026-08-15)

| check | result |
| --- | --- |
| message union identical (145 types, by TypeName set) | PASS |
| lay-over itself absent from the union | PASS |
| every word inherits the lay-over | PASS 145/145 |
| `type_name_value()` returns the Literal default | PASS 145/145 |
| no `model_config` leaked into any word | PASS |
| component-type discovery unchanged | PASS |
| payload round-trips; wire form byte-identical | PASS |

Full suite against the patched package: **193 passed, 1 skipped** — same as
baseline. Confirmed the patched copy was the one imported
(`gwsproto.__file__` under the scratch dir), not the editable install.

## Scope of the claim

Verified: the lay-over is inert with respect to gwproto's discriminator
machinery and to every word's pydantic config, across all 145 words, and
the in-process suite stays green. NOT verified here: a real broker or box
boot. The lay-over changes no wire bytes and no union membership, so the
EDD bench bar belongs to the `HydronicLayout` sema-fication that consumes
it, not to this base.
