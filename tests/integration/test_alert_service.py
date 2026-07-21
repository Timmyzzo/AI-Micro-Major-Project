"""M5 alert service integration over verified M2 and M4 fixtures."""

from pathlib import Path

from powerinsight.services.alert_service import AlertService
from powerinsight.services.forecast_service import ForecastService
from tests.data.forecasting import prepare_forecast_fixture
from tests.data.runtime import make_runtime_context


def test_alert_service_combines_three_classes_and_exports_contract(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    model = prepare_forecast_fixture(context)
    forecast_service = ForecastService(context)
    result = forecast_service.predict(
        model_id=model.model_id,
        forecast_start=forecast_service.inspect_availability().origins[0],
        requested_device="cpu",
        allow_cache=False,
    )
    result.forecast.loc[0, "y_true_kw"] = 8.0
    evaluation = AlertService(context).evaluate(result)
    exported = evaluation.export_frame()

    assert {"rule", "residual"} <= {item.alert_type for item in evaluation.alerts}
    assert tuple(exported.columns[:5]) == (
        "alert_id",
        "alert_type",
        "severity",
        "start_time",
        "end_time",
    )
    assert exported["dataset_id"].nunique() == 1
    assert evaluation.thresholds.source == "training median + MAD"
