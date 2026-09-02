def valid_image:
  (.name | type == "string") and
  (.digest | type == "string") and
  (.digest | test("^sha256:[0-9a-f]{64}$"));

def image_uri($name):
  [
    .results.images[]
    | select(.name | test("/" + $name + ":[0-9a-f]{40}$"))
    | "\(.name)@\(.digest)"
  ]
  | if length == 1 then .[0] else error("imagem ausente ou duplicada: " + $name) end;

if (
  .status == "SUCCESS" and
  (.id | type == "string") and
  (.substitutions.COMMIT_SHA | test("^[0-9a-f]{40}$")) and
  (.results.images | type == "array") and
  (.results.images | length == 5) and
  all(.results.images[]; valid_image)
) then
  {
    build_id: .id,
    git_sha: .substitutions.COMMIT_SHA,
    images: {
      batch: image_uri("batch"),
      dbt: image_uri("dbt"),
      producer: image_uri("producer"),
      dataflow_template: image_uri("dataflow-template"),
      dataflow_sdk: image_uri("dataflow-sdk")
    }
  }
else
  error("resultado do Cloud Build sem cinco imagens imutáveis")
end
