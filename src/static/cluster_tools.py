import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples, silhouette_score


def _ensure_2d_array(data: pd.DataFrame | np.ndarray) -> np.ndarray:
    arr = np.asarray(data)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


def get_silhouette_scores(
    features: pd.DataFrame | np.ndarray,
    min_clusters: int = 2,
    max_clusters: int = 20,
    random_state: int = 0,
    n_init: int = 10,
) -> tuple[dict[int, float], dict[int, float]]:
    """Return (mean_scores, min_scores) for silhouette_samples across cluster counts.

    - Validates input and bounds max number of clusters by n_samples - 1.
    - Uses silhouette_samples to compute per-sample scores and stores mean & min.
    """
    X = _ensure_2d_array(features)
    n_samples = X.shape[0]
    if n_samples < 2:
        raise ValueError("Need at least 2 samples to compute silhouette scores.")

    max_k = min(max_clusters, n_samples - 1)
    if max_k < min_clusters:
        raise ValueError("max_clusters is smaller than min_clusters given the number of samples.")

    mean_scores: dict[int, float] = {}
    min_scores: dict[int, float] = {}

    for k in range(min_clusters, max_k + 1):
        km = KMeans(n_clusters=k, random_state=random_state, n_init=n_init)
        labels = km.fit_predict(X)
        # silhouette_samples requires at least 2 distinct labels; KMeans should produce k clusters
        scores = silhouette_samples(X, labels, metric="euclidean")
        mean_scores[k] = float(np.mean(scores))
        min_scores[k] = float(np.min(scores))

    return mean_scores, min_scores


def plot_silhouette_range(
    data: pd.DataFrame | np.ndarray,
    min_clusters: int = 2,
    max_clusters: int = 20,
    random_state: int = 42,
    n_init: int = 10,
    figsize: tuple = (15, 8),
) -> tuple[plt.Figure, dict[int, float]]:
    """Compute silhouette_score for a range of cluster counts, plot the results and return (fig, scores_dict).

    - Adapts max cluster to n_samples - 1.
    - Returns both the matplotlib Figure and the dict of average silhouette scores.
    """
    X = _ensure_2d_array(data)
    n_samples = X.shape[0]
    if n_samples < 2:
        raise ValueError("Need at least 2 samples to compute silhouette scores.")

    max_k = min(max_clusters, n_samples - 1)
    if max_k < min_clusters:
        raise ValueError("max_clusters is smaller than min_clusters given the number of samples.")

    results: dict[int, float] = {}
    for k in range(min_clusters, max_k + 1):
        km = KMeans(n_clusters=k, random_state=random_state, n_init=n_init)
        labels = km.fit_predict(X)
        # silhouette_score gives the average value directly
        avg = float(silhouette_score(X, labels))
        results[k] = avg

    if not results:
        raise RuntimeError("No silhouette scores were computed.")

    # Plot
    fig, ax = plt.subplots(figsize=figsize)
    xs = list(results.keys())
    ys = [results[k] for k in xs]
    ax.plot(xs, ys, "-o")
    best_k = max(results, key=results.get)
    ax.axvline(x=best_k, color="r", linestyle="--", label=f"best: {best_k}")

    ax.set_xlabel("Number of clusters")
    ax.set_ylabel("Average silhouette score")
    ax.set_title(f"Best silhouette: {results[best_k]:.3f} at {best_k} clusters")
    ax.set_xticks(list(range(min_clusters, max_k + 1)))
    ax.xaxis.set_major_locator(ticker.FixedLocator(list(range(min_clusters, max_k + 1))))
    ax.grid(False)
    ax.legend()
    fig.tight_layout()

    return fig, results
