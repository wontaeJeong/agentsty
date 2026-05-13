{{- define "agentcask.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentcask.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "agentcask.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentcask.labels" -}}
helm.sh/chart: {{ include "agentcask.chart" . }}
app.kubernetes.io/name: {{ include "agentcask.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: agentcask
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "agentcask.componentLabels" -}}
{{ include "agentcask.labels" .root }}
app.kubernetes.io/component: {{ .component }}
app: {{ .app | default .component }}
{{- end -}}

{{- define "agentcask.systemNamespace" -}}
{{- .Values.namespaces.system.name -}}
{{- end -}}

{{- define "agentcask.sessionNamespace" -}}
{{- .Values.namespaces.sessions.name -}}
{{- end -}}

{{- define "agentcask.image" -}}
{{- $tag := default .root.Chart.AppVersion .image.tag -}}
{{- printf "%s:%s" .image.repository $tag -}}
{{- end -}}

{{- define "agentcask.runtimeImage" -}}
{{- $tag := default .Chart.AppVersion .Values.controller.runtimeImage.tag -}}
{{- printf "%s:%s" .Values.controller.runtimeImage.repository $tag -}}
{{- end -}}

{{- define "agentcask.rbacName" -}}
{{- printf "%s-%s" (include "agentcask.fullname" .root) .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentcask.sessionTokenSecretName" -}}
{{- if .Values.sessionToken.existingSecret.name -}}
{{- .Values.sessionToken.existingSecret.name -}}
{{- else -}}
{{- .Values.sessionToken.secretName -}}
{{- end -}}
{{- end -}}

{{- define "agentcask.sessionTokenSecretKey" -}}
{{- if .Values.sessionToken.existingSecret.name -}}
{{- .Values.sessionToken.existingSecret.key -}}
{{- else -}}
{{- .Values.sessionToken.key -}}
{{- end -}}
{{- end -}}

{{- define "agentcask.upstreamSecretName" -}}
{{- if .Values.modelProxy.upstream.existingSecret.name -}}
{{- .Values.modelProxy.upstream.existingSecret.name -}}
{{- else -}}
{{- .Values.modelProxy.upstream.secretName -}}
{{- end -}}
{{- end -}}

{{- define "agentcask.upstreamSecretKey" -}}
{{- if .Values.modelProxy.upstream.existingSecret.name -}}
{{- .Values.modelProxy.upstream.existingSecret.key -}}
{{- else -}}
{{- .Values.modelProxy.upstream.key -}}
{{- end -}}
{{- end -}}

{{- define "agentcask.modelProxyURL" -}}
{{- if .Values.controller.modelProxyURL -}}
{{- .Values.controller.modelProxyURL -}}
{{- else -}}
{{- printf "http://%s.%s.svc.cluster.local:%v/internal/model-proxy/v1" .Values.modelProxy.name (include "agentcask.systemNamespace" .) .Values.modelProxy.service.port -}}
{{- end -}}
{{- end -}}
