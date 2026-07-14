// CI/CD for buyer-api, run as a Multibranch Pipeline job.
//
// Every branch (including PRs) runs the two test stages. Only main
// additionally builds+pushes images, deploys to staging, then gates a
// production deploy behind a manual approval. Jenkins and both deploy
// targets live on the same VM, so deploys are a direct `sh` step, not SSH.
//
// See CLAUDE.md's "CI/CD (Jenkins)" section for the one-time setup this
// assumes: the `ghcr-credentials` Jenkins credential (GitHub username + a
// PAT with write:packages), and deploy/staging.env + deploy/prod.env
// already populated at DEPLOY_ENV_DIR (a persistent volume path outside
// this job's workspace -- see docker-compose.jenkins.yml).
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    environment {
        IMAGE          = 'ghcr.io/gregswieringa/buyer-api'
        POSTGRES_IMAGE = 'ghcr.io/gregswieringa/buyer-api-postgres'
        IMAGE_TAG      = "${env.GIT_COMMIT.take(12)}"
        DEPLOY_ENV_DIR = '/var/jenkins_home/deploy-env'
    }

    stages {
        stage('Unit tests') {
            steps {
                dir('services/buyer-api') {
                    sh '''
                        python3 -m venv .venv
                        . .venv/bin/activate
                        pip install -q -r requirements-dev.txt
                        pytest -q
                    '''
                }
            }
        }

        stage('Integration tests') {
            steps {
                // Builds services/buyer-api and db/ into
                // buyerapi-it-buyer-api:latest / buyerapi-it-postgres:latest
                // (via docker-compose.test.yml), runs the suite against a
                // real Postgres, tears the stack down. `down -v` removes
                // containers/volumes/network but not the images, so both
                // stay in the local Docker daemon's cache for the Push
                // stage below -- build once, test that exact artifact,
                // deploy that exact artifact.
                sh './scripts/integration-test.sh'
            }
        }

        stage('Push images') {
            when { branch 'main' }
            steps {
                sh """
                    docker tag buyerapi-it-buyer-api:latest ${IMAGE}:${IMAGE_TAG}
                    docker tag buyerapi-it-postgres:latest ${POSTGRES_IMAGE}:${IMAGE_TAG}
                """
                withCredentials([usernamePassword(
                    credentialsId: 'ghcr-credentials',
                    usernameVariable: 'REGISTRY_USER',
                    passwordVariable: 'REGISTRY_TOKEN'
                )]) {
                    sh '''
                        echo "$REGISTRY_TOKEN" | docker login ghcr.io -u "$REGISTRY_USER" --password-stdin
                        docker push "$IMAGE:$IMAGE_TAG"
                        docker push "$POSTGRES_IMAGE:$IMAGE_TAG"
                    '''
                }
            }
        }

        stage('Deploy to staging') {
            when { branch 'main' }
            steps {
                sh "./scripts/deploy.sh staging ${IMAGE_TAG}"
            }
        }

        stage('Promote to production') {
            when { branch 'main' }
            steps {
                input message: "Deploy ${IMAGE_TAG} to production?", ok: 'Deploy'
                sh "./scripts/deploy.sh prod ${IMAGE_TAG}"
            }
        }
    }
}
