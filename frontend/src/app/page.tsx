"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AuditResult = {
  id: string;
  question_text: string;
  status: string;
  evidence: string;
};

export default function Home() {
  const [policyFiles, setPolicyFiles] = useState<FileList | null>(null);
  const [auditFile, setAuditFile] = useState<File | null>(null);
  const [ingestProgress, setIngestProgress] = useState(0);
  const [auditProgress, setAuditProgress] = useState(0);
  const [results, setResults] = useState<AuditResult[]>([]);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isAuditing, setIsAuditing] = useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  useEffect(() => {
    // Fetch any previously generated results when the app loads
    const fetchExistingResults = async () => {
      try {
        const res = await fetch(`${API_URL}/api/results`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.length > 0) {
            setResults(data);
            setIngestProgress(100); // Assuming if there are results, a policy was already ingested
          }
        }
      } catch (error) {
        console.error("Failed to fetch initial results:", error);
      } finally {
        setIsInitialLoading(false);
      }
    };
    fetchExistingResults();
  }, []);

  const handlePolicyIngest = async () => {
    if (!policyFiles || policyFiles.length === 0) {
      toast.error("No files selected", { description: "Please select one or more policy PDFs." });
      return;
    }
    
    setIsIngesting(true);
    setIngestProgress(20);
    
    const formData = new FormData();
    // Append all selected files to the form data
    Array.from(policyFiles).forEach((file) => {
      formData.append("files", file);
    });

    try {
      const response = await fetch(`${API_URL}/api/ingest-policy`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Failed to ingest policy documents");
      
      const data = await response.json();
      setIngestProgress(100);
      toast.success("Success", { description: data.message || `Ingested ${policyFiles.length} documents successfully.` });
    } catch (error: any) {
      toast.error("Error", { description: error.message });
      setIngestProgress(0);
    } finally {
      setIsIngesting(false);
    }
  };

  const handleAuditRun = async () => {
    if (!auditFile) {
      toast.error("No file selected", { description: "Please select an audit questions PDF first." });
      return;
    }

    setIsAuditing(true);
    setAuditProgress(20);

    const formData = new FormData();
    formData.append("file", auditFile);

    try {
      const response = await fetch(`${API_URL}/api/run-audit`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Failed to run audit");

      const data = await response.json();
      setAuditProgress(100);
      setResults(data.results);
      toast.success("Audit Complete", { description: data.message || `Processed ${data.results.length} questions.` });
    } catch (error: any) {
      toast.error("Error", { description: error.message });
      setAuditProgress(0);
    } finally {
      setIsAuditing(false);
    }
  };

  const handleReset = async () => {
    try {
      await fetch(`${API_URL}/api/reset`, { method: "POST" });
      setResults([]);
      setPolicyFiles(null);
      setAuditFile(null);
      setIngestProgress(0);
      setAuditProgress(0);
      setExpandedRow(null);
      toast.success("Reset", { description: "Database and UI have been reset." });
    } catch (error: any) {
      toast.error("Error", { description: "Failed to reset database" });
    }
  };

  return (
    <main className="container mx-auto py-12 px-6 max-w-6xl space-y-10 bg-white min-h-screen">
      <div className="flex items-center justify-between pb-6 border-b border-slate-200">
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight text-slate-900">Compliance Auditor</h1>
          <p className="text-lg text-slate-600 mt-2"></p>
        </div>
        <Button 
          variant="outline" 
          onClick={handleReset}
          className="border-slate-300 text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition-colors shadow-sm"
        >
          Reset All Data
        </Button>
      </div>

      <div className="grid md:grid-cols-2 gap-8">
        {/* Phase 1: Policy Ingestion */}
        <Card className="border border-slate-200 shadow-md hover:shadow-lg transition-shadow bg-white rounded-xl">
          <CardHeader className="bg-slate-50 border-b border-slate-100 pb-5 rounded-t-xl">
            <CardTitle className="text-xl font-bold text-slate-800">1. Upload Policies</CardTitle>
            <CardDescription className="text-sm text-slate-500 mt-1">
              Upload one or multiple policy PDFs (or a whole folder) to embed in the knowledge base.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 pt-6">
            <div className="space-y-3">
              <Label htmlFor="policy-file" className="text-sm font-semibold text-slate-700">Policy PDF(s)</Label>
              <Input 
                id="policy-file" 
                type="file" 
                accept="application/pdf"
                multiple
                className="cursor-pointer file:cursor-pointer file:bg-slate-100 file:border-none file:text-slate-700 file:font-semibold file:px-4 file:py-2 file:rounded-md hover:file:bg-slate-200 transition-colors"
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPolicyFiles(e.target.files)}
                // @ts-expect-error - webkitdirectory is valid for directory uploads but not typed
                webkitdirectory=""
              />
              <p className="text-xs text-muted-foreground mt-1">Select multiple files to upload an entire directory of PDFs.</p>
            </div>
            
            {isIngesting && (
              <div className="flex flex-col items-center justify-center space-y-3 py-4">
                <Loader2 className="h-8 w-8 animate-spin text-slate-600" />
                <p className="text-sm font-medium text-slate-500 animate-pulse">This may take a couple minutes...</p>
              </div>
            )}
            
            <Button 
              className="w-full bg-slate-800 hover:bg-slate-900 text-white font-semibold transition-colors shadow-sm" 
              onClick={handlePolicyIngest} 
              disabled={!policyFiles || policyFiles.length === 0 || isIngesting}
            >
              {isIngesting ? "Ingesting Policies..." : ingestProgress === 100 ? "Policies Ingested" : "Ingest Policies"}
            </Button>
          </CardContent>
        </Card>

        {/* Phase 2-4: Audit Questions & Evaluation */}
        <Card className="border border-slate-200 shadow-md hover:shadow-lg transition-shadow bg-white rounded-xl">
          <CardHeader className="bg-slate-50 border-b border-slate-100 pb-5 rounded-t-xl">
            <CardTitle className="text-xl font-bold text-slate-800">2. Upload Audit Questions</CardTitle>
            <CardDescription className="text-sm text-slate-500 mt-1">
              Upload the PDF containing audit questions to run against the ingested policy.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 pt-6">
            <div className="space-y-3">
              <Label htmlFor="audit-file" className="text-sm font-semibold text-slate-700">Audit Questions PDF</Label>
              <Input 
                id="audit-file" 
                type="file" 
                accept="application/pdf"
                className="cursor-pointer file:cursor-pointer file:bg-blue-50 file:text-blue-700 file:border-none file:font-semibold file:px-4 file:py-2 file:rounded-md hover:file:bg-blue-100 transition-colors"
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setAuditFile(e.target.files?.[0] || null)}
              />
            </div>

            {isAuditing && (
              <div className="flex flex-col items-center justify-center space-y-3 py-4">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                <p className="text-sm font-medium text-blue-500 animate-pulse">This may take a couple minutes...</p>
              </div>
            )}

              <Button 
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors shadow-sm" 
                onClick={handleAuditRun}
                disabled={!auditFile || isAuditing}
              >
                {isAuditing ? "Running Audit Analysis..." : "Run Compliance Audit"}
              </Button>
          </CardContent>
        </Card>
      </div>

      {/* Results Section */}
      {results.length > 0 && (
        <Card className="border border-slate-200 shadow-xl bg-white rounded-xl overflow-hidden mt-8">
          <CardHeader className="bg-slate-50 border-b border-slate-100 pb-5">
            <CardTitle className="text-2xl font-bold text-slate-800">Audit Results</CardTitle>
            <CardDescription className="text-base text-slate-500 mt-1">
              
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-hidden">
              <Table className="w-full table-fixed overflow-hidden">
                <TableHeader className="bg-slate-100/50">
                  <TableRow>
                  <TableHead className="w-[35%] text-slate-700 font-semibold px-6 py-4">Question</TableHead>
                  <TableHead className="w-[15%] text-slate-700 font-semibold px-6 py-4">Status</TableHead>
                  <TableHead className="w-[50%] text-slate-700 font-semibold px-6 py-4">Evidence / Rationale</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((r) => {
                  const isExpanded = expandedRow === r.id;
                  return (
                    <TableRow 
                      key={r.id} 
                      className="hover:bg-blue-50/30 transition-colors border-b border-slate-100 last:border-0 cursor-pointer group"
                      onClick={() => setExpandedRow(isExpanded ? null : r.id)}
                    >
                      <TableCell className="font-medium text-slate-900 leading-relaxed px-6 py-5 align-top">
                        <div className={`break-words ${isExpanded ? "whitespace-normal" : "line-clamp-2"}`} title={r.question_text}>
                          {r.question_text}
                        </div>
                      </TableCell>
                      <TableCell className="px-6 py-5 align-top">
                        <Badge 
                          variant="outline" 
                          className={`text-sm font-semibold border px-3 py-1 rounded-full whitespace-nowrap ${
                            r.status.toLowerCase() === "met" 
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700" 
                              : "border-rose-200 bg-rose-50 text-rose-700"
                          }`}
                        >
                          {r.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-slate-700 leading-relaxed border-l border-slate-100 px-6 py-5 bg-slate-50/50 align-top">
                        <div className={`break-words ${isExpanded ? "whitespace-pre-wrap" : "line-clamp-3"}`}>
                          {r.evidence}
                        </div>
                        {!isExpanded && (
                          <div className="text-blue-600/70 text-xs mt-2 font-medium opacity-0 group-hover:opacity-100 transition-opacity">Click row to expand...</div>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    )}
    </main>
  );
}
