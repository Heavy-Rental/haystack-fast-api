"""FR-010 steps 1–3: Haystack intake front pipeline components."""

from app.pipelines.expand_quantity import ExpandQuantityComponent, expand_needs_to_unit_dicts
from app.pipelines.intake_front import build_intake_front_pipeline, run_intake_front
from app.pipelines.need_decomposer_component import NeedDecomposerComponent
from app.pipelines.source_text_resolver import SourceTextResolver
from app.schemas.recommendations import DecomposedNeed
from app.services.need_decomposer import StubNeedDecomposer


class _FixedDecomposer:
    def __init__(self, needs: list[DecomposedNeed]) -> None:
        self._needs = needs

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        assert source_text
        return list(self._needs)


def test_source_text_resolver_project_only() -> None:
    c = SourceTextResolver()
    out = c.run(project_text="  hello  ", file_text=None)
    assert out == {"source_text": "hello"}


def test_source_text_resolver_file_then_project() -> None:
    c = SourceTextResolver()
    out = c.run(project_text="from form", file_text="from file")
    assert out["source_text"] == "from file\n\nfrom form"


def test_source_text_resolver_empty() -> None:
    c = SourceTextResolver()
    out = c.run(project_text="  ", file_text=None)
    assert out == {"source_text": ""}


def test_expand_quantity_one() -> None:
    units = expand_needs_to_unit_dicts(
        [{"need_id": "need_1", "description": "Scissors", "quantity": 1}]
    )
    assert len(units) == 1
    assert units[0]["need_id"] == "need_1"


def test_expand_quantity_two() -> None:
    units = expand_needs_to_unit_dicts(
        [
            {
                "need_id": "need_1",
                "description": "Scissors lift",
                "equipment_hints": ["scissors lift"],
                "quantity": 2,
            }
        ]
    )
    assert [u["need_id"] for u in units] == ["need_1__u1", "need_1__u2"]
    assert "quantity" not in units[0]


def test_expand_quantity_component_empty_list() -> None:
    c = ExpandQuantityComponent()
    assert c.run(needs=[]) == {"unit_needs": []}
    assert c.run(needs=None) == {"unit_needs": []}


def test_need_decomposer_component_stub() -> None:
    c = NeedDecomposerComponent(decomposer=StubNeedDecomposer())
    out = c.run(source_text="Need a forklift")
    assert len(out["needs"]) == 1
    assert out["needs"][0]["need_id"] == "need_1"
    assert out["needs"][0]["quantity"] == 1


def test_need_decomposer_component_empty() -> None:
    c = NeedDecomposerComponent()
    assert c.run(source_text="  ") == {"needs": []}


def test_intake_front_pipeline_end_to_end_stub() -> None:
    pipeline = build_intake_front_pipeline()
    units = run_intake_front(pipeline, project_text="Indoor work ~8m")
    assert len(units) == 1
    assert units[0]["need_id"] == "need_1"
    assert units[0]["description"] == "Indoor work ~8m"


def test_intake_front_pipeline_quantity_expansion() -> None:
    pipeline = build_intake_front_pipeline(
        decomposer=_FixedDecomposer(
            [
                DecomposedNeed(
                    need_id="need_1",
                    description="Scissors lift indoor",
                    quantity=2,
                )
            ]
        )
    )
    units = run_intake_front(pipeline, project_text="two scissors lifts")
    assert [u["need_id"] for u in units] == ["need_1__u1", "need_1__u2"]


def test_intake_front_pipeline_multi_need() -> None:
    pipeline = build_intake_front_pipeline(
        decomposer=_FixedDecomposer(
            [
                DecomposedNeed(need_id="need_1", description="Scissors", quantity=1),
                DecomposedNeed(need_id="need_2", description="Excavator", quantity=1),
            ]
        )
    )
    units = run_intake_front(pipeline, project_text="scissors and excavator")
    assert [u["need_id"] for u in units] == ["need_1", "need_2"]


def test_intake_front_empty_source_yields_no_units() -> None:
    pipeline = build_intake_front_pipeline()
    units = run_intake_front(pipeline, project_text="  ", file_text=None)
    assert units == []
