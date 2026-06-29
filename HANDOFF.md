# Handoff — slacheck (consolidation des papiers ISSRE 2026)

Document de reprise pour continuer la **consolidation des deux versions du papier** dans une
nouvelle session. Lis aussi `CLAUDE.md`, `docs/paper_mapping.md`, `docs/datadog_api_catalog.md`.

## But du projet (rappel)

`slacheck` implémente **deux versions** du papier *"What SLA Can I Commit To?"* :
- **V1** (`ISSRE_2026__...Applications.pdf`, 3 pages) : série, error-budget conjonctif, décomposition
  uniforme. **C'est le contrat de non-régression gelé** — ne jamais changer son code/ses chiffres.
- **V2** (`ISSRE_2026__What_SLA_Can_I_Commit_To__v2.pdf`, 5 pages) : DAG à arêtes typées
  conjonctif/disjonctif, opérateurs sensibles à la topologie, marges γ → enveloppe A_commit,
  décomposition pondérée par in-degree, reconfiguration (machines à états).

Objectif global : **consolider le papier pour qu'il soit accepté**. Sélection de version par
`--paper-version v1|v2` (défaut v1).

## État actuel (à jour, poussé sur GitHub `Wassbdr/slcmca`, HEAD ~6a56776)

- **109 tests passent, ruff + mypy propres.** Lance toujours `pytest && ruff check . && mypy` avant/après.
- Architecture en couches : `envelope/` est **pur** (aucun import datadog/networkx) ; Datadog derrière
  `datadog/source.py` (backends `fixture` / `live` / `declared`). Voir `CLAUDE.md` "Architecture rule".
- **V2 complet** (`envelope/v2/`) : operators_v2, aggregate_v2 (propagation bottom-up topologique),
  margins, decompose_v2, reconfig, evaluate_v2. Dispatch v1/v2 dans `envelope/dispatch.py` +
  `pipeline.analyze(paper_version=…)`.
- **Audit fait + corrigé** (commits "Audit fixes P0/P1/P2") : latence disjonctive (min-branche),
  reconfig conscient de l'action (scale_up/down), harness d'éval honnête, DependencyGraph durci
  (acyclicité/entrypoint/arêtes validés à la construction), marges γ par métrique, etc.
- **Table I reproduite honnêtement** : `slacheck eval --both` → v1 10/57/0, v2 10/60/43 ; les 3 ratés
  v1 sont exactement les cas `sub_gap` (hétérogènes). LaTeX : `slacheck eval --latex`.
- **Pont live Datadog fonctionne** (voir ci-dessous).

## Le live Datadog — RÉSOLU (ce qui a pris du temps)

Cluster `observit-cluster1` (org **devolab**, site `datadoghq.com`). Mon train-ticket tourne dans le
namespace **`tt-slacheck`** (déployé via `deploy/tt-slacheck/`, instrumenté APM auto-injection).

**Le "blocage APM" était un faux diagnostic.** L'ingestion marchait ; il manquait juste **du trafic**
sur l'instance (sans requêtes, aucun appel inter-service tracé → 0 arête). Après génération de trafic,
les vraies arêtes apparaissent (ts-ui-dashboard→ts-auth, ts-travel→ts-route/train/ticketinfo…).

**Pour relancer le live :**
```bash
# .env doit avoir DD_ENV=devolab (l'agent tague tout en env:devolab, PAS slacheck)
# 1) générer du trafic (sinon pas d'arêtes) :
kubectl port-forward -n tt-slacheck svc/ts-ui-dashboard 18080:8080 &
#    login + travel query en boucle (voir historique) ; attendre ~2 min l'agrégation
# 2) analyse V2 live filtrée sur train-ticket uniquement :
DD_ENV=devolab slacheck analyze --source live --paper-version v2 \
  -e ts-ui-dashboard -c availability \
  --service-prefix ts- --exclude-contains with-jaeger \
  --pricing fixtures/scenarios/pricing.example.yaml
```
- **Topologie** : live APM (filtre `--service-prefix ts-` car la map renvoie ~215 services du cluster).
- **Disponibilité** : proxy k8s readiness (`replicas_ready/desired`) quand l'APM n'en donne pas.
- **Coût** : modèle k8s (`cpu/mem.requests × pricing.yaml`) — Datadog n'a pas de coût par-service.
- **Latence** : `None` tant que peu de trafic ; les métriques `trace.servlet.request.duration`
  s'agrègent avec plus de requêtes réussies.

Source `declared` (`fixtures/topology/train-ticket.yaml`) = solution de repli si l'APM est vide.

## Pistes pour continuer la consolidation (par valeur)

1. **Latence live** : générer plus de trafic réussi (travel queries) pour que
   `trace.servlet.request.duration` s'agrège, et confirmer que slacheck remonte une vraie latence p99
   par service via `metrics.collect_with_samples` (vérifier le namespace de métrique réel :
   `trace.servlet.request` vs `trace.http.request`).
2. **Reconfiguration §IV.E plus réaliste** : les stratégies sont des fixtures ; on pourrait dériver de
   vrais triggers d'élasticité (HPA k8s) et les confronter aux SLO.
3. **Dashboard live** : `slacheck publish` (a `dashboards_write`) pour pousser le verdict V2 réel dans
   Datadog — `dashboard/builder.py` est prêt (note A_commit + groupe Resource Health k8s).
4. **Affiner l'éval** : le dataset (`fixtures/eval/`, généré par `scripts/gen_eval.py`) est une démo de
   la mécanique, pas un benchmark — documenté honnêtement. Si le papier change ses chiffres, régénérer.
5. **Fidélité math restante** : tout l'audit est corrigé ; la latence mixte conj+disj est testée
   (`test_aggregate_v2`). Re-vérifier contre le PDF V2 si des formules évoluent.

## Conventions à respecter

- **Ne jamais toucher V1** (operators/aggregate/decompose/faults + leurs tests = contrat gelé).
- `envelope/` reste **pur**. Datadog uniquement derrière `source.py`.
- TDD : test rouge d'abord pour toute correction de fidélité.
- **Aucune mention d'IA/Claude** dans les commits/PR/commentaires (préférence utilisateur).
- Secrets : `.env` jamais commité ; ne jamais coller de clé en chat.
- Ne pas re-déclencher un rollout massif de `tt-slacheck` (42 deploys d'un coup → containerd sature,
  long à converger ; étaler ou faire `rollout restart` séquentiel).

## Fichiers clés

- `src/slacheck/envelope/v2/` — moteur V2 pur.
- `src/slacheck/datadog/{source,live_client,declared_client,metrics}.py` — acquisition + proxies k8s.
- `src/slacheck/graph/{builder,critical_path,typed_graph}.py` — graphe, filtre, projection DependencyGraph.
- `src/slacheck/eval/runner.py` + `fixtures/eval/` + `scripts/gen_eval.py` — Table I.
- `docs/paper_mapping.md` — mapping V1/V2 ↔ code (à tenir à jour si le papier bouge).
