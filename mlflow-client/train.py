import mlflow
import mlflow.sklearn

from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score
)

# ----------------------------
# MLflow configuration
# ----------------------------
mlflow.set_tracking_uri("http://<EC2_PUBLIC_IP>:5000")
mlflow.set_experiment("sklearn-classification-baseline")

# ----------------------------
# Data
# ----------------------------
X, y = load_iris(return_X_y=True)

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.6,
    random_state=42,
    stratify=y
)

# ----------------------------
# Model
# ----------------------------
n_estimators = 100
max_depth = 5

model = RandomForestClassifier(
    n_estimators=n_estimators,
    max_depth=max_depth,
    random_state=42
)

model.fit(X_train, y_train)

# ----------------------------
# Evaluation
# ----------------------------
y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred, average="macro")
recall = recall_score(y_test, y_pred, average="macro")
f1 = f1_score(y_test, y_pred, average="macro")

# ----------------------------
# MLflow logging
# ----------------------------
with mlflow.start_run(run_name="run_2"):

    # Parameters
    mlflow.log_param("model_type", "RandomForestClassifier")
    mlflow.log_param("n_estimators", n_estimators)
    mlflow.log_param("max_depth", max_depth)
    mlflow.log_param("dataset", "iris")

    # Metrics
    mlflow.log_metric("accuracy", accuracy)
    mlflow.log_metric("precision_macro", precision)
    mlflow.log_metric("recall_macro", recall)
    mlflow.log_metric("f1_macro", f1)

    # Model artifact
    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model"
    )

print("Run completed")
print(f"Accuracy : {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall   : {recall:.4f}")
print(f"F1-score : {f1:.4f}")
