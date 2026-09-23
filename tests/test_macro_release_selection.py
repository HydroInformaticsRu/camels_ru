"""Check release selection without opening the full release or recomputing signatures."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from coldregion_robustness import load_subset  # noqa: E402
import verify_macros as verifier  # noqa: E402


def test_release_selection() -> None:
    """CLI selection and the imported subset loader must use the same release."""
    temp_root = ROOT / ".tmp"
    temp_root.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=temp_root) as tmp:
        release = Path(tmp)
        (release / "camels_ru_signatures.csv").write_text("gauge_id,is_anomalous\n987654,False\n")
        (release / "camels_ru_attributes.csv").write_text(
            "gauge_id,dor_pc_pva,snw_pc_uyr,prm_pc_use,tmp_dc_uyr\n987654,0,20,35,-5\n"
        )
        (release / "camels_ru_gauge_summary.csv").write_text("gauge_id,overall_grade\n987654,B\n")
        subset = load_subset(release_dir=release)
        assert subset["gauge_id"].tolist() == ["987654"]
        assert subset["prm_pc_use"].tolist() == [35]
        assert subset["overall_grade"].tolist() == ["B"]

        class StopBeforeDataReadsError(Exception):
            pass

        original = verifier.RELEASE
        try:
            for args, expected in (
                (["--release-dir", str(release)], release),
                ([], ROOT / "release" / "CAMELS_RU_v1.0"),
            ):
                with (
                    patch.object(sys, "argv", ["verify_macros.py", *args]),
                    patch.object(verifier, "parse_macros", side_effect=StopBeforeDataReadsError),
                ):
                    try:
                        verifier.main()
                    except StopBeforeDataReadsError:
                        pass
                assert verifier.RELEASE == expected

            verifier.RELEASE = release
            with patch.object(verifier, "load_subset", side_effect=StopBeforeDataReadsError) as loader:
                try:
                    verifier.check_coldregion_macros({})
                except StopBeforeDataReadsError:
                    pass
                loader.assert_called_once_with(release_dir=release)
            verifier.check_year_flags_gates(verifier.pd.DataFrame())
            assert verifier._FAILURES == ["required release year_flags evidence"]
            try:
                verifier.report_drift_summary()
            except SystemExit as error:
                assert error.code == 1
            else:
                raise AssertionError("Missing required release evidence must fail verification")
            verifier._FAILURES.clear()
            verifier.report_skip("SKIP optional audit evidence unavailable")
            assert verifier._SKIPPED == ["SKIP optional audit evidence unavailable"]
            verifier.report_drift_summary()
        finally:
            verifier.RELEASE = original
            verifier._FAILURES.clear()
            verifier._SKIPPED.clear()


if __name__ == "__main__":
    test_release_selection()
    print("Release selection checks passed.")
