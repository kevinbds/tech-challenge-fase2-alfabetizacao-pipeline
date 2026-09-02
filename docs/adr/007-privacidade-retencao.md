# ADR 007 — Privacidade e retenção

**Status:** aceito.

`id_aluno` é tratado como pseudônimo. Permanece apenas em landing, Bronze,
staging, quarentena e Silver restritos; Gold, outras saídas de consumo, logs e
evidências usam agregados. Landing
fica elegível para exclusão em sete dias, raw e quarentena em 30 dias, e tabelas
criadas no Silver restrito expiram em 365 dias. Lifecycle no GCS é assíncrono:
essas idades não garantem o instante da remoção. Landing, streaming e Dataflow
desligam versionamento e soft delete; após o `Delete` concluído, não mantêm cópia
recuperável no bucket. Bronze não tem lifecycle no baseline e é preservado até o
teardown autorizado. Manifests de controle ficam elegíveis em 730 dias; como o
bucket `control` preserva versionamento e soft delete, suas gerações continuam
recuperáveis além desse marco conforme a janela dessas proteções.

Alternativas rejeitadas: chamar identificador de anonimizado reduz a proteção;
reter tudo indefinidamente amplia exposição. Trade-off: preservar Bronze melhora
reprodução histórica, mas exige controle de acesso contínuo; reter manifests só
até a elegibilidade aos 730 dias limita a janela garantida de auditoria, embora
as proteções do bucket estendam a recuperação. Outro prazo exige ajuste de
política antes do apply.
