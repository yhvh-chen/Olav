'use client';

import { useState, useEffect } from 'react';
import { useAuthStore } from '@/lib/stores/auth-store';
import { getInspections, getInspection, updateInspection, runInspection } from '@/lib/api/client';
import type { InspectionConfig } from '@/lib/api/types';

interface InspectionModalProps {
  onClose: () => void;
}

export function InspectionModal({ onClose }: InspectionModalProps) {
  const { token } = useAuthStore();
  const [inspections, setInspections] = useState<InspectionConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [yamlContent, setYamlContent] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState('');

  useEffect(() => {
    if (!token) return;
    loadInspections();
  }, [token]);

  const loadInspections = async () => {
    if (!token) return;
    try {
      const data = await getInspections(token);
      setInspections(data.inspections);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSelect = async (id: string) => {
    setSelectedId(id);
    if (!token) return;
    try {
      const config = await getInspection(id, token);
      // Note: In a real implementation, we should fetch the raw YAML content.
      // Here we are just stringifying the JSON as a placeholder for the editor.
      setYamlContent(JSON.stringify(config, null, 2));
    } catch (err) {
      console.error(err);
    }
  };

  const handleSave = async () => {
    if (!token || !selectedId) return;
    try {
      await updateInspection(selectedId, yamlContent, token);
      setStatus('Saved successfully');
      setTimeout(() => setStatus(''), 3000);
    } catch (err) {
      setStatus('Failed to save');
    }
  };

  const handleRun = async () => {
    if (!token || !selectedId) return;
    setIsRunning(true);
    try {
      await runInspection(selectedId, token);
      setStatus('Inspection started');
    } catch (err) {
      setStatus('Failed to start');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex h-[80vh] w-full max-w-4xl flex-col rounded-lg bg-background shadow-xl">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="text-lg font-semibold">Inspection Manager</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        
        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <div className="w-64 border-r border-border overflow-y-auto p-2">
            {inspections.map(insp => (
              <button
                key={insp.id}
                onClick={() => handleSelect(insp.id)}
                className={`w-full rounded px-3 py-2 text-left text-sm hover:bg-secondary ${selectedId === insp.id ? 'bg-secondary' : ''}`}
              >
                {insp.name}
              </button>
            ))}
          </div>
          
          {/* Editor */}
          <div className="flex flex-1 flex-col p-4">
            {selectedId ? (
              <>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{status}</span>
                  <div className="flex gap-2">
                    <button
                      onClick={handleSave}
                      className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground hover:bg-primary/90"
                    >
                      Save
                    </button>
                    <button
                      onClick={handleRun}
                      disabled={isRunning}
                      className="rounded bg-green-600 px-3 py-1 text-sm text-white hover:bg-green-700 disabled:opacity-50"
                    >
                      {isRunning ? 'Running...' : 'Run'}
                    </button>
                  </div>
                </div>
                <textarea
                  value={yamlContent}
                  onChange={(e) => setYamlContent(e.target.value)}
                  className="flex-1 resize-none rounded border border-input bg-muted p-4 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  spellCheck={false}
                />
              </>
            ) : (
              <div className="flex h-full items-center justify-center text-muted-foreground">
                Select an inspection to edit
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
