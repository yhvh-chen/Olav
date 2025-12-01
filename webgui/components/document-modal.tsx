'use client';

import { useState, useEffect } from 'react';
import { useAuthStore } from '@/lib/stores/auth-store';
import { getDocuments, uploadDocument, deleteDocument } from '@/lib/api/client';
import type { DocumentSummary } from '@/lib/api/types';

interface DocumentModalProps {
  onClose: () => void;
}

export function DocumentModal({ onClose }: DocumentModalProps) {
  const { token } = useAuthStore();
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    if (!token) return;
    loadDocuments();
  }, [token]);

  const loadDocuments = async () => {
    if (!token) return;
    try {
      const data = await getDocuments(token);
      setDocuments(data.documents);
    } catch (err) {
      console.error(err);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!token || !e.target.files?.[0]) return;
    setIsUploading(true);
    try {
      await uploadDocument(e.target.files[0], token);
      await loadDocuments();
    } catch (err) {
      console.error(err);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!token) return;
    if (!confirm('Are you sure you want to delete this document?')) return;
    try {
      await deleteDocument(id, token);
      await loadDocuments();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex h-[80vh] w-full max-w-4xl flex-col rounded-lg bg-background shadow-xl">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="text-lg font-semibold">Document Manager</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        
        <div className="p-4">
          <div className="mb-4 flex items-center gap-4">
            <label className="cursor-pointer rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              {isUploading ? 'Uploading...' : 'Upload Document'}
              <input
                type="file"
                className="hidden"
                onChange={handleUpload}
                disabled={isUploading}
                accept=".pdf,.docx,.txt,.md"
              />
            </label>
            <span className="text-xs text-muted-foreground">Supported: PDF, DOCX, TXT, MD</span>
          </div>

          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Filename</th>
                  <th className="px-4 py-2 text-left font-medium">Size</th>
                  <th className="px-4 py-2 text-left font-medium">Uploaded</th>
                  <th className="px-4 py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {documents.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                      No documents found
                    </td>
                  </tr>
                ) : (
                  documents.map((doc) => (
                    <tr key={doc.id} className="hover:bg-secondary/50">
                      <td className="px-4 py-2">{doc.filename}</td>
                      <td className="px-4 py-2">{(doc.size_bytes / 1024).toFixed(1)} KB</td>
                      <td className="px-4 py-2">{new Date(doc.uploaded_at).toLocaleDateString()}</td>
                      <td className="px-4 py-2 text-right">
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="text-red-500 hover:text-red-600"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
