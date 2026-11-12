# Business Standard Intelligence Cloud Engine ⚡

Autonomous high-throughput cloud harvester operating 100% on GitHub Actions (0% local disk/RAM). Streams and archives the complete historical database of **Business Standard** (2015–2026, ~12 Lakh articles) partitioned across 4 private storage vaults.

---

## 🏛️ Storage Topology (4 Partitioned Vaults)

| Repository | Period Covered | Estimated Volume | Visibility | Format |
|---|---|---|---|---|
| [`business-standard-vault-1`](https://github.com/parshant65-lang/business-standard-vault-1) | **2015 – 2017** | ~3,00,000 articles | **Private 🔒** | Compressed `.json.gz` |
| [`business-standard-vault-2`](https://github.com/parshant65-lang/business-standard-vault-2) | **2018 – 2020** | ~3,00,000 articles | **Private 🔒** | Compressed `.json.gz` |
| [`business-standard-vault-3`](https://github.com/parshant65-lang/business-standard-vault-3) | **2021 – 2023** | ~3,00,000 articles | **Private 🔒** | Compressed `.json.gz` |
| [`business-standard-vault-4`](https://github.com/parshant65-lang/business-standard-vault-4) | **2024 – 2026** | ~3,00,000 articles | **Private 🔒** | Compressed `.json.gz` |

---

## ⚙️ Architecture & Features

1. **Next.js Deep State Extraction**:
   - Extracts complete pristine article bodies directly from `<script id="__NEXT_DATA__">`, bypassing paywall client-side restrictions.
2. **Multi-Threaded Concurrency**:
   - Uses 10 worker threads per cloud runner for ~10 articles/sec throughput on Azure 1 Gbps networking.
3. **Automated Sequential Rollover**:
   - Ingests chronologically month-by-month; when Vault 1 (2015–2017) finishes, automatically rolls over to Vault 2, then Vault 3, then Vault 4.
4. **Auto-Chain Dispatch Loop**:
   - Re-triggers workflow dispatch sequentially, running non-stop on free GitHub Actions cloud runners.
