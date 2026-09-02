#!/usr/bin/env bash
set -euo pipefail

# マウントしたボリュームの所有者をvscodeユーザーに揃える
sudo chown -R vscode:vscode /home/vscode

# uvを公式から導入
curl -LsSf https://astral.sh/uv/install.sh | sh

# gitleaksを公式から導入
GITLEAKS_VERSION="8.30.1"
GITLEAKS_TARBALL="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
curl -LsSf -o "/tmp/${GITLEAKS_TARBALL}" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${GITLEAKS_TARBALL}"
curl -LsSf -o "/tmp/gitleaks_checksums.txt" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_checksums.txt"
(cd /tmp && grep "${GITLEAKS_TARBALL}" gitleaks_checksums.txt | sha256sum -c -)
sudo tar -xzf "/tmp/${GITLEAKS_TARBALL}" -C /usr/local/bin gitleaks
rm -f "/tmp/${GITLEAKS_TARBALL}" "/tmp/gitleaks_checksums.txt"

# pyproject.tomlのパッケージを.venvに同期
"$HOME/.local/bin/uv" sync

# pre-commitのgitフックを有効化
"$HOME/.local/bin/uv" run pre-commit install

# Claude Codeのプラグインマーケットプレイスを登録
# (.claude/settings.jsonのenabledPluginsを有効化するために必要)
claude plugin marketplace add aws/agent-toolkit-for-aws
claude plugin install aws-core@agent-toolkit-for-aws --scope project

claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install superpowers@claude-plugins-official --scope project
