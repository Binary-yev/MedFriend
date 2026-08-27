# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
}

resource "google_storage_bucket" "logs_data_bucket" {
  name                        = "${var.project_id}-${var.project_name}-logs"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true

  depends_on = [resource.google_project_service.services]
}

# Runtime object access, scoped to this one bucket.
#
# The app never creates, deletes, or re-configures a bucket: Terraform creates
# this one, and GcsArtifactService only ever calls upload/get/list/delete on
# BLOBS inside it (see care_navigator/app_utils/services.py). Telemetry likewise
# only writes objects under gs://<bucket>/<path>. So objectAdmin here replaces
# the project-wide roles/storage.admin the app SA used to carry, which also
# granted authority over every other bucket in the project.
resource "google_storage_bucket_iam_member" "app_sa_logs_bucket_object_admin" {
  bucket = google_storage_bucket.logs_data_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app_sa.email}"
}
