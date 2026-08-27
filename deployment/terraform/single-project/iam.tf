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

locals {
  project_ids = {
    default = var.project_id
  }
}


# Get the project number
data "google_project" "project" {
  project_id = var.project_id
}

# DEPLOY-TIME identity, not the runtime one. Grants the default compute service
# account the Cloud Build builder role so `gcloud run deploy --source` can build
# and push the image. This is the broadest grant in this file and it is on a
# SHARED default identity -- narrowing it means moving the build to a dedicated
# build SA, which depends on the pipeline you deploy from. The runtime identity
# (google_service_account.app_sa below) is separate and least-privilege.
# NOTE: the resource name is a historical misnomer -- the role granted is
# cloudbuild.builds.builder, not Storage Object Creator. Renaming it would
# re-address state and force a destroy/create of the binding, so it is left
# as-is deliberately.
resource "google_project_iam_member" "default_compute_sa_storage_object_creator" {
  project    = var.project_id
  role       = "roles/cloudbuild.builds.builder"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  depends_on = [resource.google_project_service.services]
}

# Agent service account
resource "google_service_account" "app_sa" {
  account_id   = "${var.project_name}-app"
  display_name = "${var.project_name} Agent Service Account"
  project      = var.project_id
  depends_on   = [resource.google_project_service.services]
}

# Grant application SA the required permissions to run the application
resource "google_project_iam_member" "app_sa_roles" {
  for_each = {
    for pair in setproduct(keys(local.project_ids), var.app_sa_roles) :
    join(",", pair) => {
      project = local.project_ids[pair[0]]
      role    = pair[1]
    }
  }

  project    = each.value.project
  role       = each.value.role
  member     = "serviceAccount:${google_service_account.app_sa.email}"
  depends_on = [resource.google_project_service.services]
}

# Grant the application SA access to Secret Manager -- per secret, not
# project-wide. The service reads exactly these three at startup (they are
# mounted into the container in service.tf), so a project-level secretAccessor
# would also hand it every secret added to this project later, by anyone.
resource "google_secret_manager_secret_iam_member" "app_sa_gmail_token_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gmail_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "app_sa_bland_key_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.bland_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "app_sa_maps_key_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.google_maps_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_sa.email}"
}

# UNCOMMENT the following block to make the Cloud Run service publicly accessible 
# (e.g. when you want to use the web interface from an unauthenticated browser).
# resource "google_cloud_run_v2_service_iam_binding" "public_invoker" {
#   project  = google_cloud_run_v2_service.app.project
#   location = google_cloud_run_v2_service.app.location
#   name     = google_cloud_run_v2_service.app.name
#   role     = "roles/run.invoker"
#   members  = ["allUsers"]
# }

