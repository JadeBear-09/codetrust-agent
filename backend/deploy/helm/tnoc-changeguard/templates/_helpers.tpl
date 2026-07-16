{{- define "tnoc.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tnoc.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "tnoc.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tnoc.labels" -}}
app.kubernetes.io/name: {{ include "tnoc.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
