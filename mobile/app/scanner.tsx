import React, { useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Image,
  FlatList,
  Alert,
  ActivityIndicator,
  Platform,
  SafeAreaView,
  Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as FileSystem from 'expo-file-system';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../src/utils/colors';
import { uploadInvoice, uploadInvoiceBatch, type PickedUpload } from '../src/services/invoiceService';
import { processExtractionResult } from '../src/services/calculations';
import { isBatchResult } from '../src/types';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const THUMB_SIZE = 56;

interface CapturedPage {
  uri: string;
  id: string;
}

export default function ScannerScreen() {
  const router = useRouter();
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();

  const [pages, setPages] = useState<CapturedPage[]>([]);
  const [flash, setFlash] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [previewUri, setPreviewUri] = useState<string | null>(null);

  // ---------- Capture a page ----------
  const capturePhoto = useCallback(async () => {
    if (!cameraRef.current || capturing) return;
    setCapturing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.85,
        skipProcessing: false,
      });
      if (photo?.uri) {
        const newPage: CapturedPage = {
          uri: photo.uri,
          id: Date.now().toString(),
        };
        setPages((prev) => [...prev, newPage]);
      }
    } catch (err) {
      Alert.alert('Capture Error', 'Failed to take photo. Please try again.');
    }
    setCapturing(false);
  }, [capturing]);

  // ---------- Remove a page ----------
  const removePage = useCallback((id: string) => {
    setPages((prev) => prev.filter((p) => p.id !== id));
    setPreviewUri(null);
  }, []);

  // ---------- Process & upload ----------
  const handleDone = useCallback(async () => {
    if (pages.length === 0) {
      Alert.alert('No Pages', 'Please capture at least one page.');
      return;
    }
    setProcessing(true);

    try {
      const stamp = Date.now();
      // Turn each captured page into an upload payload (a File blob on web).
      const toPicked = async (uri: string, idx: number): Promise<PickedUpload> => {
        const name = `scan_${stamp}_${idx + 1}.jpg`;
        let file: File | null = null;
        if (Platform.OS === 'web') {
          try {
            const resp = await fetch(uri);
            const blob = await resp.blob();
            file = new File([blob], name, { type: 'image/jpeg' });
          } catch {
            // Fall back to uri-based upload
          }
        }
        return { uri, name, mimeType: 'image/jpeg', file };
      };
      const picked = await Promise.all(pages.map((p, i) => toPicked(p.uri, i)));

      if (picked.length === 1) {
        // Single page → keep the review screen.
        const raw = await uploadInvoice(picked[0]);
        setProcessing(false);
        if (isBatchResult(raw)) {
          router.replace({
            pathname: '/(tabs)/invoices',
            params: { newIds: raw.invoices.map((i) => i.id).join(',') },
          });
        } else {
          router.replace({
            pathname: '/extraction-results',
            params: { data: JSON.stringify(processExtractionResult(raw)), fileName: picked[0].name, pageCount: '1' },
          });
        }
      } else {
        // Several pages → merged into ONE document server-side (and split if it
        // actually holds multiple invoices) → saved as drafts, land on inbox.
        const batch = await uploadInvoiceBatch(picked);
        setProcessing(false);
        if (!batch.invoices?.length) {
          throw new Error('No invoice could be read from the scanned pages.');
        }
        router.replace({
          pathname: '/(tabs)/invoices',
          params: { newIds: batch.invoices.map((i) => i.id).join(',') },
        });
      }
    } catch (err: any) {
      setProcessing(false);
      const msg = err.response?.data?.detail || err.message || 'Processing failed';
      Alert.alert('Processing Error', msg);
    }
  }, [pages, router]);

  // ---------- Permission handling ----------
  if (!permission) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={colors.brand[400]} />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permissionContainer}>
        <View style={styles.permissionContent}>
          <View style={styles.permissionIcon}>
            <Ionicons name="camera-outline" size={48} color={colors.brand[400]} />
          </View>
          <Text style={styles.permissionTitle}>Camera Access</Text>
          <Text style={styles.permissionText}>
            Cognivend needs camera access to scan invoice pages. Your photos are
            only used for invoice processing and never stored beyond your session.
          </Text>
          <TouchableOpacity style={styles.permissionBtn} onPress={requestPermission}>
            <Text style={styles.permissionBtnText}>Grant Permission</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
            <Text style={styles.backBtnText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ---------- Processing overlay ----------
  if (processing) {
    return (
      <View style={styles.processingOverlay}>
        <ActivityIndicator size="large" color="#fff" />
        <Text style={styles.processingText}>Processing {pages.length} page{pages.length > 1 ? 's' : ''}...</Text>
        <Text style={styles.processingHint}>Extracting invoice data with AI</Text>
      </View>
    );
  }

  // ---------- Full-screen preview ----------
  if (previewUri) {
    const page = pages.find((p) => p.uri === previewUri);
    return (
      <SafeAreaView style={styles.previewContainer}>
        <Image source={{ uri: previewUri }} style={styles.previewImage} resizeMode="contain" />
        <View style={styles.previewActions}>
          <TouchableOpacity
            style={styles.previewBtn}
            onPress={() => setPreviewUri(null)}
          >
            <Ionicons name="arrow-back" size={20} color="#fff" />
            <Text style={styles.previewBtnText}>Back</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.previewBtn, styles.previewDeleteBtn]}
            onPress={() => page && removePage(page.id)}
          >
            <Ionicons name="trash-outline" size={20} color="#fff" />
            <Text style={styles.previewBtnText}>Delete</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ---------- Main camera view ----------
  return (
    <View style={styles.container}>
      <CameraView
        ref={cameraRef}
        style={styles.camera}
        facing="back"
        flash={flash ? 'on' : 'off'}
      >
        {/* Top bar */}
        <SafeAreaView style={styles.topBar}>
          <TouchableOpacity style={styles.topBtn} onPress={() => router.back()}>
            <Ionicons name="close" size={26} color="#fff" />
          </TouchableOpacity>

          <View style={styles.pageCounter}>
            <Ionicons name="documents-outline" size={16} color="#fff" />
            <Text style={styles.pageCountText}>
              {pages.length} page{pages.length !== 1 ? 's' : ''}
            </Text>
          </View>

          <TouchableOpacity style={styles.topBtn} onPress={() => setFlash(!flash)}>
            <Ionicons
              name={flash ? 'flash' : 'flash-off'}
              size={22}
              color={flash ? '#FFD60A' : '#fff'}
            />
          </TouchableOpacity>
        </SafeAreaView>

        {/* Scan frame overlay */}
        <View style={styles.scanFrame}>
          <View style={[styles.corner, styles.cornerTL]} />
          <View style={[styles.corner, styles.cornerTR]} />
          <View style={[styles.corner, styles.cornerBL]} />
          <View style={[styles.corner, styles.cornerBR]} />
        </View>

        <Text style={styles.scanHint}>
          Align invoice within the frame
        </Text>

        {/* Bottom controls */}
        <View style={styles.bottomBar}>
          {/* Thumbnail strip */}
          {pages.length > 0 && (
            <FlatList
              data={pages}
              horizontal
              showsHorizontalScrollIndicator={false}
              keyExtractor={(item) => item.id}
              style={styles.thumbStrip}
              contentContainerStyle={styles.thumbStripContent}
              renderItem={({ item, index }) => (
                <TouchableOpacity
                  style={styles.thumbWrap}
                  onPress={() => setPreviewUri(item.uri)}
                  activeOpacity={0.8}
                >
                  <Image source={{ uri: item.uri }} style={styles.thumb} />
                  <View style={styles.thumbBadge}>
                    <Text style={styles.thumbBadgeText}>{index + 1}</Text>
                  </View>
                </TouchableOpacity>
              )}
            />
          )}

          {/* Capture row */}
          <View style={styles.captureRow}>
            {/* Spacer left — or retake hint */}
            <View style={styles.captureRowSide} />

            {/* Shutter button */}
            <TouchableOpacity
              style={styles.shutterOuter}
              onPress={capturePhoto}
              disabled={capturing}
              activeOpacity={0.7}
            >
              <View style={[styles.shutterInner, capturing && styles.shutterCapturing]} />
            </TouchableOpacity>

            {/* Done button */}
            <View style={styles.captureRowSide}>
              {pages.length > 0 && (
                <TouchableOpacity style={styles.doneBtn} onPress={handleDone}>
                  <Text style={styles.doneBtnText}>Done</Text>
                  <Ionicons name="checkmark" size={18} color="#fff" />
                </TouchableOpacity>
              )}
            </View>
          </View>
        </View>
      </CameraView>
    </View>
  );
}

const CORNER_SIZE = 28;
const CORNER_THICKNESS = 3;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },

  // Top bar
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 8,
  },
  topBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(0,0,0,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pageCounter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(0,0,0,0.4)',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  pageCountText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
  },

  // Scan frame
  scanFrame: {
    flex: 1,
    marginHorizontal: 32,
    marginVertical: 40,
    position: 'relative',
  },
  corner: {
    position: 'absolute',
    width: CORNER_SIZE,
    height: CORNER_SIZE,
  },
  cornerTL: {
    top: 0,
    left: 0,
    borderTopWidth: CORNER_THICKNESS,
    borderLeftWidth: CORNER_THICKNESS,
    borderColor: '#fff',
    borderTopLeftRadius: 4,
  },
  cornerTR: {
    top: 0,
    right: 0,
    borderTopWidth: CORNER_THICKNESS,
    borderRightWidth: CORNER_THICKNESS,
    borderColor: '#fff',
    borderTopRightRadius: 4,
  },
  cornerBL: {
    bottom: 0,
    left: 0,
    borderBottomWidth: CORNER_THICKNESS,
    borderLeftWidth: CORNER_THICKNESS,
    borderColor: '#fff',
    borderBottomLeftRadius: 4,
  },
  cornerBR: {
    bottom: 0,
    right: 0,
    borderBottomWidth: CORNER_THICKNESS,
    borderRightWidth: CORNER_THICKNESS,
    borderColor: '#fff',
    borderBottomRightRadius: 4,
  },
  scanHint: {
    textAlign: 'center',
    color: 'rgba(255,255,255,0.6)',
    fontSize: 13,
    fontWeight: '500',
    marginBottom: 8,
  },

  // Bottom bar
  bottomBar: {
    paddingBottom: Platform.OS === 'ios' ? 34 : 20,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  thumbStrip: {
    maxHeight: THUMB_SIZE + 16,
  },
  thumbStripContent: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 8,
  },
  thumbWrap: {
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    borderRadius: 8,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.5)',
  },
  thumb: {
    width: '100%',
    height: '100%',
  },
  thumbBadge: {
    position: 'absolute',
    top: 2,
    right: 2,
    backgroundColor: colors.brand[400],
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  thumbBadgeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#fff',
  },

  // Capture row
  captureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 32,
    paddingTop: 12,
  },
  captureRowSide: {
    width: 80,
    alignItems: 'center',
  },
  shutterOuter: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 4,
    borderColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterInner: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: '#fff',
  },
  shutterCapturing: {
    backgroundColor: colors.brand[400],
    transform: [{ scale: 0.85 }],
  },
  doneBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.brand[400],
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  doneBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#fff',
  },

  // Permission screen
  permissionContainer: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  permissionContent: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
  },
  permissionIcon: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: 'rgba(46,163,242,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  permissionTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 12,
  },
  permissionText: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.55)',
    textAlign: 'center',
    lineHeight: 21,
    marginBottom: 32,
  },
  permissionBtn: {
    backgroundColor: colors.brand[400],
    borderRadius: 14,
    paddingHorizontal: 32,
    paddingVertical: 14,
    marginBottom: 12,
  },
  permissionBtnText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
  },
  backBtn: {
    paddingVertical: 10,
  },
  backBtnText: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.45)',
    fontWeight: '500',
  },

  // Processing overlay
  processingOverlay: {
    flex: 1,
    backgroundColor: '#0A1628',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
  processingText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#fff',
  },
  processingHint: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.45)',
  },

  // Preview
  previewContainer: {
    flex: 1,
    backgroundColor: '#000',
  },
  previewImage: {
    flex: 1,
  },
  previewActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingVertical: 16,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  previewBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  previewDeleteBtn: {
    backgroundColor: 'rgba(255,59,48,0.7)',
  },
  previewBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
});
