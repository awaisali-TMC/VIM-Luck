import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';
import { hapticSuccess, hapticError, hapticLight } from '../../src/utils/haptics';
import { fmtFileSize } from '../../src/utils/formatters';
import useExtraction from '../../src/hooks/useExtraction';
import type { PickedUpload } from '../../src/services/invoiceService';

const ACCEPTED_TYPES = [
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/tiff',
];

type SelectedFile = PickedUpload & { size: number };

export default function UploadScreen() {
  const router = useRouter();
  const { file, result, batch, loading, error, selectFile, extract, extractFiles, reset } = useExtraction();
  // Local list of picked files. 1 file → single-extract (may still split into a
  // batch if it holds several invoices); several files → batch upload.
  const [selected, setSelected] = React.useState<SelectedFile[]>([]);

  const pickFile = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ACCEPTED_TYPES,
        copyToCacheDirectory: true,
        multiple: true,
      });

      if (res.canceled || !res.assets?.length) return;

      const tooBig = res.assets.find((a) => a.size && a.size > 20 * 1024 * 1024);
      if (tooBig) {
        Alert.alert('File Too Large', 'Each file must be 20 MB or less.');
        return;
      }

      const mapped: SelectedFile[] = res.assets.map((asset) => ({
        uri: asset.uri,
        name: asset.name,
        size: asset.size || 0,
        mimeType: asset.mimeType || 'application/pdf',
        file: (asset as any).file || null, // Web: native File object
      }));

      hapticLight();
      setSelected(mapped);
      // Prime the single-extract path when exactly one file is chosen; otherwise
      // clear it so the batch path drives from `selected`.
      if (mapped.length === 1) selectFile(mapped[0]);
      else reset();
    } catch (err) {
      Alert.alert('Error', 'Failed to pick file');
    }
  };

  const handleExtract = async () => {
    if (selected.length > 1) await extractFiles(selected);
    else await extract();
  };

  const clearSelection = () => {
    reset();
    setSelected([]);
  };

  // Single invoice → review screen.
  React.useEffect(() => {
    if (result) {
      hapticSuccess();
      router.push({
        pathname: '/extraction-results',
        params: { data: JSON.stringify(result), fileName: file?.name || '' },
      });
    }
  }, [result]);

  // A file with several invoices, or several files, were saved as drafts →
  // skip the review screen and land on the inbox with them highlighted.
  React.useEffect(() => {
    if (batch) {
      hapticSuccess();
      const ids = (batch.invoices || []).map((i) => i.id).join(',');
      setSelected([]);
      router.replace({
        pathname: '/(tabs)/invoices',
        params: { newIds: ids },
      });
    }
  }, [batch]);

  React.useEffect(() => {
    if (error) hapticError();
  }, [error]);

  const count = selected.length;
  const title = count > 1 ? `${count} files selected` : count === 1 ? selected[0].name : 'Tap to select file(s)';
  const subtitle = count > 1
    ? `${fmtFileSize(selected.reduce((s, f) => s + (f.size || 0), 0))} total · will be saved as drafts`
    : count === 1
    ? fmtFileSize(selected[0].size)
    : 'PDF, JPEG, PNG, TIFF — pick one or several — Max 20 MB each';

  return (
    <View style={styles.container}>
      {/* Drop Zone */}
      <TouchableOpacity style={styles.dropZone} onPress={pickFile} activeOpacity={0.7} disabled={loading}>
        <View style={styles.iconCircle}>
          <Ionicons name="cloud-upload-outline" size={36} color={colors.brand[400]} />
        </View>
        <Text style={styles.dropTitle}>{title}</Text>
        <Text style={styles.dropSubtitle}>{subtitle}</Text>
      </TouchableOpacity>

      {/* Error */}
      {error && (
        <View style={styles.errorBox}>
          <Ionicons name="alert-circle" size={18} color={colors.danger.dark} />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* Actions */}
      <View style={styles.actions}>
        {count > 0 && !loading && (
          <TouchableOpacity style={styles.btnSecondary} onPress={clearSelection}>
            <Text style={styles.btnSecondaryText}>Clear</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={[styles.btnPrimary, (count === 0 || loading) && styles.btnDisabled]}
          onPress={handleExtract}
          disabled={count === 0 || loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Ionicons name={count > 1 ? 'cloud-upload-outline' : 'scan-outline'} size={18} color="#fff" />
          )}
          <Text style={styles.btnPrimaryText}>
            {loading
              ? (count > 1 ? 'Uploading...' : 'Extracting...')
              : (count > 1 ? `Upload ${count} files` : 'Extract with AI')}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Processing info */}
      {loading && (
        <Text style={styles.processingHint}>
          {count > 1
            ? 'Uploading and extracting each invoice — a few minutes for a large batch.'
            : 'AI is processing your file. A multi-invoice file is split automatically.'}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: colors.neutral[50],
  },
  dropZone: {
    backgroundColor: '#fff',
    borderRadius: 16,
    borderWidth: 2,
    borderColor: colors.brand[200],
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 48,
    paddingHorizontal: 24,
    marginTop: 20,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.brand[50],
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  dropTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.neutral[800],
    textAlign: 'center',
    marginBottom: 6,
  },
  dropSubtitle: {
    fontSize: 12,
    color: colors.neutral[400],
    textAlign: 'center',
  },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.danger.bg,
    borderRadius: 10,
    padding: 12,
    marginTop: 16,
  },
  errorText: {
    fontSize: 13,
    color: colors.danger.dark,
    flex: 1,
  },
  actions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 24,
  },
  btnPrimary: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: colors.brand[500],
    borderRadius: 12,
    paddingVertical: 14,
  },
  btnPrimaryText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#fff',
  },
  btnDisabled: {
    opacity: 0.5,
  },
  btnSecondary: {
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderRadius: 12,
    backgroundColor: colors.neutral[100],
    justifyContent: 'center',
  },
  btnSecondaryText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.neutral[600],
  },
  processingHint: {
    fontSize: 12,
    color: colors.neutral[400],
    textAlign: 'center',
    marginTop: 16,
  },
});
