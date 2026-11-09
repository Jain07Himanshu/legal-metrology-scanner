/**
 * Legal Metrology Product Scanner - Multi-Image / Multi-Side Scanner Client
 */

const { useState, useEffect, useRef } = React;
const API_BASE = window.location.origin;

function LegalMetrologySimpleApp() {
  const [activeTab, setActiveTab] = useState("scan"); // 'scan' | 'result' | 'history'
  const [samples, setSamples] = useState([]);
  
  // Scanning Source State
  const [scanMode, setScanMode] = useState("upload"); // 'upload' | 'camera' | 'sample'
  
  // Multi-Image List: [{ id, dataUrl, label, ocrText }]
  const [uploadedImages, setUploadedImages] = useState([]);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);
  const [selectedSample, setSelectedSample] = useState(null);
  
  // Scanner Engine State
  const [isScanning, setIsScanning] = useState(false);
  const [scanStep, setScanStep] = useState("");
  const [scanResult, setScanResult] = useState(null);
  const [activeHighlight, setActiveHighlight] = useState(null);
  const [resultImageTab, setResultImageTab] = useState(0);
  
  // Camera State
  const [isCameraActive, setIsCameraActive] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [cameraStream, setCameraStream] = useState(null);

  // History State
  const [historyList, setHistoryList] = useState([]);
  
  // Show-Cause Notice Modal
  const [noticeModalOpen, setNoticeModalOpen] = useState(false);
  const [noticeData, setNoticeData] = useState(null);
  const [isGeneratingNotice, setIsGeneratingNotice] = useState(false);

  // Declaration Analysis Tab State
  const [declarationFilter, setDeclarationFilter] = useState("all"); // all|issue|review|pass
  const [expandedEvidence, setExpandedEvidence] = useState(null);    // declaration_id or null

  // Load benchmark samples on start
  useEffect(() => {
    fetchSamples();
    fetchHistory();
  }, []);

  const fetchSamples = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/samples`);
      if (res.ok) {
        const data = await res.json();
        setSamples(data);
      }
    } catch (e) {
      console.error("Failed to load benchmark samples:", e);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/history`);
      if (res.ok) {
        const data = await res.json();
        setHistoryList(data);
      }
    } catch (e) {
      console.error("Failed to load history:", e);
    }
  };

  // Handle selecting a preset sample
  const handleSelectSample = (sample) => {
    setSelectedSample(sample);
    setScanMode("sample");
    stopCamera();

    const newImages = [];
    const rendered = sample.rendered_images || {};
    const sides = sample.sides || {};

    const sideOrder = ["front", "back", "top", "side"];
    sideOrder.forEach((sideKey, idx) => {
      if (rendered[sideKey] || sides[sideKey]) {
        newImages.push({
          id: `sample_${sample.id}_${sideKey}`,
          dataUrl: rendered[sideKey] || null,
          label: `${sideKey.toUpperCase()} Panel`,
          ocrText: sides[sideKey] || ""
        });
      }
    });

    setUploadedImages(newImages);
    setSelectedImageIndex(0);
  };

  // Handle Multi-File Upload (allows selecting multiple files simultaneously)
  const handleMultipleFilesUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    setScanMode("upload");
    setSelectedSample(null);
    stopCamera();

    const readFilesPromises = files.map((file, idx) => {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (ev) => {
          resolve({
            id: `upload_${Date.now()}_${idx}_${Math.random()}`,
            dataUrl: ev.target.result,
            label: `Photo ${uploadedImages.length + idx + 1}`,
            ocrText: ""
          });
        };
        reader.readAsDataURL(file);
      });
    });

    const newUploaded = await Promise.all(readFilesPromises);
    setUploadedImages(prev => [...prev, ...newUploaded]);
    setSelectedImageIndex(uploadedImages.length); // switch preview to newly added
  };

  // Remove a single image from upload list
  const handleRemoveImage = (indexToRemove, e) => {
    e.stopPropagation();
    setUploadedImages(prev => prev.filter((_, idx) => idx !== indexToRemove));
    if (selectedImageIndex >= indexToRemove && selectedImageIndex > 0) {
      setSelectedImageIndex(selectedImageIndex - 1);
    }
  };

  // Clear all images
  const handleClearAllImages = () => {
    setUploadedImages([]);
    setSelectedImageIndex(0);
    setSelectedSample(null);
  };

  // Camera Management
  const startCamera = async () => {
    setScanMode("camera");
    setSelectedSample(null);
    setIsCameraActive(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      setCameraStream(stream);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err) {
      alert("Camera access was not granted. Please select or drag photos below.");
      setIsCameraActive(false);
      setScanMode("upload");
    }
  };

  const stopCamera = () => {
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop());
      setCameraStream(null);
    }
    setIsCameraActive(false);
  };

  const captureCameraPhoto = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 800;
    canvas.height = video.videoHeight || 600;
    
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    
    const newImageItem = {
      id: `cam_${Date.now()}`,
      dataUrl: dataUrl,
      label: `Camera Snap ${uploadedImages.length + 1}`,
      ocrText: ""
    };

    setUploadedImages(prev => [...prev, newImageItem]);
    setSelectedImageIndex(uploadedImages.length);
  };

  const [isOcrProcessing, setIsOcrProcessing] = useState(false);
  const [showOcrEditor, setShowOcrEditor] = useState(true);

  // Run Tesseract OCR on a specific photo on demand
  const runOcrOnSingleImage = async (index) => {
    if (!uploadedImages[index] || !uploadedImages[index].dataUrl) return;
    const imgItem = uploadedImages[index];
    if (!window.Tesseract) {
      alert("Tesseract OCR engine is initializing. Please try again in a moment.");
      return;
    }
    setIsOcrProcessing(true);
    setScanStep(`Running OCR on ${imgItem.label}...`);
    try {
      const res = await Tesseract.recognize(imgItem.dataUrl, 'eng');
      const text = res?.data?.text || "";
      setUploadedImages(prev => prev.map((item, idx) => idx === index ? { ...item, ocrText: text } : item));
    } catch (err) {
      console.warn("OCR recognition error:", err);
    } finally {
      setIsOcrProcessing(false);
      setScanStep("");
    }
  };

  // Update OCR text for a specific photo manually
  const handleUpdatePhotoText = (index, newText) => {
    setUploadedImages(prev => prev.map((item, idx) => idx === index ? { ...item, ocrText: newText } : item));
  };

  // Run End-to-End Multi-Image Compliance Scan
  const handleExecuteScan = async () => {
    if (uploadedImages.length === 0) {
      alert("Please upload or capture at least 1 product image first!");
      return;
    }

    setIsScanning(true);
    setScanStep(`Preprocessing ${uploadedImages.length} image(s)...`);

    try {
      // 1. Run in-browser Tesseract OCR on any image that doesn't have OCR text yet
      const updatedImages = [...uploadedImages];
      for (let i = 0; i < updatedImages.length; i++) {
        const img = updatedImages[i];
        if ((!img.ocrText || !img.ocrText.trim()) && window.Tesseract && img.dataUrl && img.dataUrl.startsWith("data:image")) {
          setScanStep(`Running OCR on ${img.label || 'Photo ' + (i+1)} (${i+1}/${updatedImages.length})...`);
          try {
            const res = await Tesseract.recognize(img.dataUrl, 'eng');
            const recognized = res?.data?.text || "";
            img.ocrText = recognized;
            updatedImages[i] = { ...img, ocrText: recognized };
          } catch (tessErr) {
            console.warn("OCR failed on photo", i, tessErr);
          }
        }
      }
      setUploadedImages(updatedImages);

      setScanStep(`Running Legal Metrology Entity Extraction across ${uploadedImages.length} image(s)...`);

      // 2. Construct multi-image payload with explicit per-side text
      const sidesMap = {};
      const sidesTextMap = {};
      const imageList = [];
      let combinedOcrText = "";

      updatedImages.forEach((img, idx) => {
        const sideKey = img.label || `Photo ${idx + 1}`;
        sidesMap[sideKey] = img.dataUrl;
        sidesTextMap[sideKey] = img.ocrText || "";
        imageList.push(img.dataUrl);
        if (img.ocrText) {
          combinedOcrText += `\n--- ${sideKey} ---\n` + img.ocrText;
        }
      });

      let payload = {
        sides: sidesMap,
        sides_text: sidesTextMap,
        images: imageList,
        ocr_text: combinedOcrText || null,
        inspector_id: "INSP-DL-4089",
        location: "Enforcement Inspection Point"
      };

      if (selectedSample) {
        payload.product_name = selectedSample.name;
        payload.brand = selectedSample.brand;
        payload.category = selectedSample.category;
      }

      setScanStep("Evaluating 10 statutory rules under Legal Metrology 2011 Rules...");
      const res = await fetch(`${API_BASE}/api/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error("Scan processing failed");
      }

      const result = await res.json();
      setScanResult(result);
      setResultImageTab(0);
      setActiveTab("result");
      fetchHistory();
    } catch (e) {
      alert("Error scanning product: " + e.message);
    } finally {
      setIsScanning(false);
      setScanStep("");
    }
  };

  const handleDraftNotice = async () => {
    if (!scanResult) return;
    setIsGeneratingNotice(true);
    try {
      const decl = scanResult.declarations;
      const payload = {
        scan_id: scanResult.scan_id,
        company_name: decl.mfr_name || scanResult.brand + " Pvt Ltd",
        company_address: decl.mfr_address || "Registered Premises, Industrial Area, New Delhi",
        recipient_designation: "Managing Director / Director in Charge",
        officer_name: "Shri R. K. Sharma",
        officer_designation: "Legal Metrology Inspector (Enforcement)",
        jurisdiction: "Central Enforcement Division, NCT of Delhi",
        notice_type: "SHOW_CAUSE"
      };

      const res = await fetch(`${API_BASE}/api/notice/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        setNoticeData(data);
        setNoticeModalOpen(true);
      }
    } catch (e) {
      alert("Error drafting notice: " + e.message);
    } finally {
      setIsGeneratingNotice(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans">
      
      {/* Top Header */}
      <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-40 shadow-lg">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-xl shadow-md shadow-blue-500/30">
              ⚖️
            </div>
            <div>
              <h1 className="font-extrabold text-white text-base sm:text-lg tracking-tight">
                Legal Metrology Scanner
              </h1>
              <p className="text-[11px] text-slate-400">
                Multi-Side Packaging Compliance Engine • 2011 Rules
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => {
                stopCamera();
                setActiveTab("scan");
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ${
                activeTab === "scan"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              <span>📸</span>
              <span>Scanner ({uploadedImages.length})</span>
            </button>

            {scanResult && (
              <button
                onClick={() => setActiveTab("result")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ${
                  activeTab === "result"
                    ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                <span>📊</span>
                <span>Audit Result</span>
              </button>
            )}

            {scanResult?.declaration_analysis && (
              <button
                onClick={() => setActiveTab("declarations")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ${
                  activeTab === "declarations"
                    ? "bg-violet-600 text-white shadow-md shadow-violet-600/30"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                <span>🔍</span>
                <span>
                  Declarations
                  {scanResult.declaration_analysis.potential_issue_count > 0 && (
                    <span className="ml-1 bg-red-500 text-white text-[9px] px-1 py-0.2 rounded-full font-mono">
                      {scanResult.declaration_analysis.potential_issue_count}
                    </span>
                  )}
                </span>
              </button>
            )}

            <button
              onClick={() => {
                stopCamera();
                fetchHistory();
                setActiveTab("history");
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ${
                activeTab === "history"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              <span>📁</span>
              <span>History</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-4 sm:p-6 space-y-6">
        
        {/* ========================================================================= */}
        {/* VIEW 1: MULTI-IMAGE SCANNER STUDIO                                        */}
        {/* ========================================================================= */}
        {activeTab === "scan" && (
          <div className="space-y-6">
            
            {/* Title & Instructions */}
            <div className="text-center space-y-1.5 pt-2">
              <h2 className="text-xl sm:text-2xl font-black text-white">
                Scan Product Packaging (Single or Multiple Images)
              </h2>
              <p className="text-xs sm:text-sm text-slate-400 max-w-xl mx-auto">
                Upload 1, 2, 4, or more photos of the product (Front, Back, MRP Side, Nutrition Panel). The scanner analyzes all images together to verify complete Legal Metrology compliance.
              </p>
            </div>

            {/* Top Source Mode Selector Bar */}
            <div className="grid grid-cols-3 gap-2 bg-slate-900/90 p-1.5 rounded-xl border border-slate-800 max-w-md mx-auto">
              <label className={`cursor-pointer py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center space-x-1.5 ${
                scanMode === "upload" && !isCameraActive
                  ? "bg-blue-600 text-white shadow"
                  : "text-slate-300 hover:bg-slate-800"
              }`}>
                <span>📁</span>
                <span>Upload Photos</span>
                <input
                  type="file"
                  multiple
                  accept="image/*"
                  onChange={handleMultipleFilesUpload}
                  className="hidden"
                />
              </label>

              <button
                onClick={startCamera}
                className={`py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center space-x-1.5 ${
                  isCameraActive
                    ? "bg-blue-600 text-white shadow"
                    : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                <span>📷</span>
                <span>Camera</span>
              </button>

              <button
                onClick={() => {
                  stopCamera();
                  setScanMode("sample");
                  if (samples.length > 0) handleSelectSample(samples[0]);
                }}
                className={`py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center space-x-1.5 ${
                  scanMode === "sample" && !isCameraActive
                    ? "bg-blue-600 text-white shadow"
                    : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                <span>⚡</span>
                <span>Demo Samples</span>
              </button>
            </div>

            {/* Live Camera Viewport if Camera Active */}
            {isCameraActive && (
              <div className="bg-slate-900 rounded-2xl border-2 border-blue-500 overflow-hidden relative max-w-xl mx-auto shadow-2xl">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  className="w-full h-72 object-cover"
                />
                <canvas ref={canvasRef} className="hidden" />

                {/* Target Frame Overlay */}
                <div className="absolute inset-6 border-2 border-dashed border-blue-400/80 rounded-xl pointer-events-none flex items-center justify-center">
                  <div className="text-[11px] bg-slate-900/90 text-blue-300 px-3 py-1 rounded-full font-mono font-semibold">
                    Position Product Panel
                  </div>
                </div>

                <div className="p-4 bg-slate-900 border-t border-slate-800 flex items-center justify-between">
                  <button
                    onClick={stopCamera}
                    className="text-xs text-slate-400 hover:text-white px-3 py-2"
                  >
                    Done / Close Camera
                  </button>
                  <button
                    onClick={captureCameraPhoto}
                    className="bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs px-6 py-2.5 rounded-xl shadow-lg flex items-center space-x-2 animate-pulse"
                  >
                    <span>📸</span>
                    <span>SNAP PHOTO (+{uploadedImages.length + 1})</span>
                  </button>
                </div>
              </div>
            )}

            {/* 1-Tap Benchmark Samples Picker (if Demo Mode) */}
            {scanMode === "sample" && !isCameraActive && (
              <div className="space-y-3">
                <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                  <span>SELECT A MULTI-PANEL PRODUCT TEST CASE:</span>
                  <span className="text-[10px] text-blue-400 font-mono">Preloaded 4-Side Data</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                  {samples.map(s => {
                    const isSelected = selectedSample?.id === s.id;
                    const isViolation = s.expected_verdict === "NON_COMPLIANT";
                    const isLab = s.expected_verdict === "FLAGGED_FOR_LAB";

                    return (
                      <div
                        key={s.id}
                        onClick={() => handleSelectSample(s)}
                        className={`p-3 rounded-xl border cursor-pointer transition-all flex items-start space-x-3 ${
                          isSelected
                            ? "bg-blue-950/60 border-blue-500 shadow-lg shadow-blue-500/20 ring-2 ring-blue-500/40"
                            : "bg-slate-900/80 border-slate-800 hover:border-slate-700 hover:bg-slate-900"
                        }`}
                      >
                        <div className="w-12 h-12 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-center text-xl shrink-0 overflow-hidden">
                          {s.rendered_images?.front ? (
                            <img src={s.rendered_images.front} className="w-full h-full object-cover" />
                          ) : (
                            <span>📦</span>
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-bold text-white truncate block">
                            {s.name}
                          </span>
                          <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                            {s.brand} • 4 Sides Included
                          </div>

                          <div className="mt-2 flex items-center space-x-1.5">
                            <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded font-bold uppercase ${
                              isViolation
                                ? "bg-red-500/20 text-red-300 border border-red-500/30"
                                : isLab
                                ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                                : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            }`}>
                              {s.expected_verdict.replace(/_/g, " ")}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Multi-Image Gallery & Drag-and-Drop Area */}
            <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-5 shadow-2xl space-y-4">
              
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center space-x-2">
                  <span className="text-sm font-bold text-white flex items-center gap-1.5">
                    <span>🖼️</span> Uploaded Packaging Images ({uploadedImages.length})
                  </span>
                  {uploadedImages.length > 0 && (
                    <span className="text-[10px] bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded font-mono font-bold">
                      Ready to Scan
                    </span>
                  )}
                </div>

                <div className="flex items-center space-x-2">
                  <label className="cursor-pointer bg-slate-800 hover:bg-slate-700 text-blue-400 hover:text-blue-300 text-xs font-bold px-3 py-1.5 rounded-lg border border-slate-700 flex items-center space-x-1 transition">
                    <span>+ Add More Photos</span>
                    <input
                      type="file"
                      multiple
                      accept="image/*"
                      onChange={handleMultipleFilesUpload}
                      className="hidden"
                    />
                  </label>
                  {uploadedImages.length > 0 && (
                    <button
                      onClick={handleClearAllImages}
                      className="text-xs text-slate-500 hover:text-red-400 px-2 py-1"
                    >
                      Clear All
                    </button>
                  )}
                </div>
              </div>

              {/* If no images uploaded yet: Large Drag-and-Drop Placeholder */}
              {uploadedImages.length === 0 ? (
                <label className="border-2 border-dashed border-slate-700 hover:border-blue-500 rounded-2xl p-8 flex flex-col items-center justify-center cursor-pointer transition bg-slate-950/50 hover:bg-slate-900/50">
                  <span className="text-4xl block mb-2">📥</span>
                  <span className="text-sm font-bold text-slate-200">
                    Click to browse or drop multiple product photos here
                  </span>
                  <span className="text-xs text-slate-500 mt-1">
                    Supports selecting multiple images at once (Front, Back, Sides, Barcode)
                  </span>
                  <input
                    type="file"
                    multiple
                    accept="image/*"
                    onChange={handleMultipleFilesUpload}
                    className="hidden"
                  />
                </label>
              ) : (
                /* Multi-Image Thumbnail Ribbon + Large Main Preview */
                <div className="space-y-4">
                  
                  {/* Thumbnail Row */}
                  <div className="flex items-center space-x-3 overflow-x-auto pb-2">
                    {uploadedImages.map((imgItem, idx) => (
                      <div
                        key={imgItem.id}
                        onClick={() => setSelectedImageIndex(idx)}
                        className={`relative w-24 h-20 rounded-xl border overflow-hidden cursor-pointer shrink-0 transition-all ${
                          selectedImageIndex === idx
                            ? "border-blue-500 ring-2 ring-blue-500 shadow-lg"
                            : "border-slate-800 hover:border-slate-700 opacity-70 hover:opacity-100"
                        }`}
                      >
                        {imgItem.dataUrl ? (
                          <img src={imgItem.dataUrl} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full bg-slate-950 flex items-center justify-center text-xs text-slate-500 font-mono">
                            {imgItem.label}
                          </div>
                        )}

                        <span className="absolute bottom-0 inset-x-0 bg-slate-900/90 text-[9px] text-center font-mono py-0.5 text-slate-300 truncate px-1">
                          {imgItem.label}
                        </span>

                        {/* Delete Button */}
                        <button
                          onClick={(e) => handleRemoveImage(idx, e)}
                          className="absolute top-1 right-1 w-4 h-4 bg-red-600 hover:bg-red-500 text-white text-[10px] rounded-full flex items-center justify-center font-bold shadow"
                          title="Remove this photo"
                        >
                          ✕
                        </button>
                      </div>
                    ))}

                    {/* Add More Thumbnail Button */}
                    <label className="w-24 h-20 rounded-xl border-2 border-dashed border-slate-700 hover:border-blue-500 flex flex-col items-center justify-center cursor-pointer shrink-0 text-slate-400 hover:text-white transition bg-slate-950/40">
                      <span className="text-xl">+</span>
                      <span className="text-[10px] font-bold">Add Photo</span>
                      <input
                        type="file"
                        multiple
                        accept="image/*"
                        onChange={handleMultipleFilesUpload}
                        className="hidden"
                      />
                    </label>
                  </div>

                  {/* Active Selected Image Preview Box */}
                  <div className="relative bg-slate-950 rounded-xl overflow-hidden border border-slate-800 min-h-[240px] max-h-[300px] flex items-center justify-center">
                    {uploadedImages[selectedImageIndex]?.dataUrl ? (
                      <img
                        src={uploadedImages[selectedImageIndex].dataUrl}
                        alt="Active Preview"
                        className="w-full h-full object-contain max-h-[300px]"
                      />
                    ) : (
                      <div className="text-slate-500 text-xs">No preview available</div>
                    )}
                    
                    <div className="absolute top-3 left-3 bg-slate-900/90 backdrop-blur px-2.5 py-1 rounded-lg text-xs font-mono border border-slate-700 text-slate-300">
                      Previewing: {uploadedImages[selectedImageIndex]?.label}
                    </div>

                    {isScanning && <div className="scan-line"></div>}
                  </div>

                  {/* Detected OCR Packaging Text Card for Selected Photo */}
                  <div className="bg-slate-950/80 rounded-xl border border-slate-800 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-slate-200 flex items-center gap-1">
                          <span>📝</span> Packaging Text ({uploadedImages[selectedImageIndex]?.label || 'Selected Photo'})
                        </span>
                        {uploadedImages[selectedImageIndex]?.ocrText ? (
                          <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.2 rounded font-mono">
                            ✓ Text Ready
                          </span>
                        ) : (
                          <span className="text-[10px] bg-yellow-500/20 text-yellow-300 px-1.5 py-0.2 rounded font-mono">
                            Pending OCR
                          </span>
                        )}
                      </div>

                      <div className="flex items-center space-x-2">
                        {uploadedImages[selectedImageIndex]?.dataUrl && (
                          <button
                            onClick={() => runOcrOnSingleImage(selectedImageIndex)}
                            disabled={isOcrProcessing}
                            className="bg-blue-600/80 hover:bg-blue-500 text-white text-[10px] font-bold px-2.5 py-1 rounded transition flex items-center space-x-1"
                          >
                            <span>⚡</span>
                            <span>{isOcrProcessing ? "Reading..." : "Re-read with OCR"}</span>
                          </button>
                        )}
                        <button
                          onClick={() => setShowOcrEditor(!showOcrEditor)}
                          className="text-[10px] text-slate-400 hover:text-slate-200"
                        >
                          {showOcrEditor ? "Hide Text ▲" : "View/Edit Text ▼"}
                        </button>
                      </div>
                    </div>

                    {showOcrEditor && (
                      <div>
                        <textarea
                          rows={4}
                          value={uploadedImages[selectedImageIndex]?.ocrText || ""}
                          onChange={(e) => handleUpdatePhotoText(selectedImageIndex, e.target.value)}
                          placeholder="Extracted text from this packaging photo (e.g. Net Qty: 500 g, MRP Rs 250, Mfg by...)"
                          className="w-full bg-slate-900 border border-slate-700/80 rounded-lg p-2 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500"
                        />
                        <div className="text-[10px] text-slate-500 flex justify-between mt-1">
                          <span>Auto-extracted via Optical Character Recognition. You can also edit/add declarations directly.</span>
                          <span className="font-mono">{uploadedImages[selectedImageIndex]?.ocrText ? `${uploadedImages[selectedImageIndex].ocrText.length} chars` : '0 chars'}</span>
                        </div>
                      </div>
                    )}
                  </div>

                </div>
              )}

              {/* Big Action Button */}
              {uploadedImages.length > 0 && (
                <button
                  onClick={handleExecuteScan}
                  disabled={isScanning}
                  className={`w-full py-4 rounded-xl font-black text-sm tracking-wide shadow-xl flex items-center justify-center space-x-2 transition-all ${
                    isScanning
                      ? "bg-slate-800 text-slate-400 cursor-wait"
                      : "bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-500 hover:from-blue-500 hover:to-indigo-500 text-white shadow-blue-500/30 hover:scale-[1.01]"
                  }`}
                >
                  {isScanning ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>{scanStep || "Analyzing all images..."}</span>
                    </>
                  ) : (
                    <>
                      <span>🔍</span>
                      <span>SCAN ALL {uploadedImages.length} IMAGE{uploadedImages.length > 1 ? 'S' : ''} & EXTRACT COMPLIANCE</span>
                    </>
                  )}
                </button>
              )}

            </div>

          </div>
        )}

        {/* ========================================================================= */}
        {/* VIEW 2: PRODUCT AUDIT RESULTS & MULTI-IMAGE VIEWER                        */}
        {/* ========================================================================= */}
        {activeTab === "result" && scanResult && (
          <div className="space-y-6">
            
            {/* 1. Big Clear Verdict Banner */}
            <div className={`p-5 rounded-2xl border shadow-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 ${
              scanResult.compliance_status === "COMPLIANT"
                ? "bg-emerald-950/60 border-emerald-500/60"
                : scanResult.compliance_status === "NON_COMPLIANT"
                ? "bg-red-950/60 border-red-500/60"
                : "bg-purple-950/60 border-purple-500/60"
            }`}>
              
              <div className="flex items-center space-x-3.5">
                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl font-black shrink-0 shadow-lg ${
                  scanResult.compliance_status === "COMPLIANT"
                    ? "bg-emerald-500 text-black"
                    : scanResult.compliance_status === "NON_COMPLIANT"
                    ? "bg-red-500 text-white"
                    : "bg-purple-500 text-white"
                }`}>
                  {scanResult.compliance_status === "COMPLIANT" ? "✓" : (scanResult.compliance_status === "NON_COMPLIANT" ? "✕" : "🧪")}
                </div>

                <div>
                  <div className="text-xl sm:text-2xl font-black text-white tracking-tight">
                    {scanResult.compliance_status === "COMPLIANT"
                      ? "100% LEGAL COMPLIANT"
                      : (scanResult.compliance_status === "NON_COMPLIANT"
                          ? `NON-COMPLIANT (${scanResult.failed_rules} VIOLATION${scanResult.failed_rules > 1 ? 'S' : ''})`
                          : "FLAGGED FOR STATUTORY LAB TESTING")}
                  </div>
                  <p className="text-xs text-slate-300 mt-0.5 leading-relaxed max-w-2xl">
                    {scanResult.summary_verdict}
                  </p>
                </div>
              </div>

              <div className="flex sm:flex-col items-center justify-center bg-slate-900/90 px-4 py-2.5 rounded-xl border border-slate-800 text-center shrink-0">
                <div className="text-2xl font-black font-mono text-white">
                  {scanResult.overall_compliance_score}%
                </div>
                <div className="text-[10px] text-slate-400 uppercase font-semibold">
                  Compliance Score
                </div>
              </div>

            </div>

            {/* 2. Action Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/80 p-3 rounded-xl border border-slate-800">
              <div className="flex items-center space-x-2">
                <a
                  href={scanResult.pdf_report_url || "#"}
                  target="_blank"
                  className="bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs px-4 py-2 rounded-lg shadow flex items-center space-x-1.5 transition"
                >
                  <span>📄</span>
                  <span>Download PDF Audit Report</span>
                </a>

                {scanResult.failed_rules > 0 && (
                  <button
                    onClick={handleDraftNotice}
                    className="bg-red-600 hover:bg-red-500 text-white font-bold text-xs px-4 py-2 rounded-lg shadow flex items-center space-x-1.5 transition"
                  >
                    <span>⚖️</span>
                    <span>Draft Show-Cause Notice</span>
                  </button>
                )}
              </div>

              <button
                onClick={() => {
                  stopCamera();
                  setActiveTab("scan");
                }}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs px-4 py-2 rounded-lg border border-slate-700 flex items-center space-x-1.5 transition"
              >
                <span>🔄</span>
                <span>Scan Another Product</span>
              </button>
            </div>

            {/* 3. Multi-Image Viewer with Bounding Boxes + Extracted Information Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* Multi-Image Switcher & Bounding Box Viewer */}
              <div className="lg:col-span-5 space-y-3">
                <div className="bg-slate-900 rounded-2xl border border-slate-800 p-4">
                  
                  {/* Photo Switcher Tabs if multiple images */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-white">SCANNED IMAGES ({uploadedImages.length})</span>
                    <div className="flex space-x-1 overflow-x-auto max-w-[200px]">
                      {uploadedImages.map((img, i) => (
                        <button
                          key={i}
                          onClick={() => setResultImageTab(i)}
                          className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold transition ${
                            resultImageTab === i
                              ? "bg-blue-600 text-white"
                              : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                          }`}
                        >
                          P{i + 1}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="relative bg-slate-950 rounded-xl overflow-hidden border border-slate-800 min-h-[300px] flex items-center justify-center">
                    {uploadedImages[resultImageTab]?.dataUrl ? (
                      <img
                        src={uploadedImages[resultImageTab].dataUrl}
                        alt="Product Photo"
                        className="w-full h-full object-contain max-h-[360px]"
                      />
                    ) : (
                      <div className="text-slate-500 text-xs">No image</div>
                    )}

                    {/* Bounding Box Highlights */}
                    {scanResult.rules_evaluated
                      .filter(r => r.bounding_box)
                      .map((r, i) => {
                        const bbox = r.bounding_box;
                        const isPass = r.status === "PASS";
                        const isHighlighted = activeHighlight === r.rule_id;

                        return (
                          <div
                            key={i}
                            style={{
                              left: `${bbox.x * 100}%`,
                              top: `${bbox.y * 100}%`,
                              width: `${bbox.width * 100}%`,
                              height: `${bbox.height * 100}%`
                            }}
                            className={`bbox-overlay ${isPass ? "bbox-pass" : ""} ${
                              isHighlighted ? "ring-4 ring-yellow-400 z-20" : ""
                            }`}
                            title={`${r.rule_name}: ${r.status}`}
                          >
                            <span className={`text-[8px] font-mono px-1 py-0.2 rounded absolute -top-3.5 left-0 font-bold ${
                              isPass ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
                            }`}>
                              {r.rule_id}
                            </span>
                          </div>
                        );
                      })}
                  </div>

                  <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 bg-emerald-500 rounded-full"></span> Compliant Field
                      <span className="w-2 h-2 bg-red-500 rounded-full ml-2"></span> Violation Detected
                    </span>
                    <span className="font-mono">{uploadedImages[resultImageTab]?.label}</span>
                  </div>
                </div>
              </div>

              {/* All Information Extracted across All Images */}
              <div className="lg:col-span-7 space-y-4">
                
                <div className="bg-slate-900 rounded-2xl border border-slate-800 p-5 space-y-4">
                  <h3 className="text-sm font-extrabold text-white flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <span>📋</span> ALL EXTRACTED DECLARATIONS (COMBINED)
                    </span>
                    <span className="text-[10px] bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded font-mono">
                      Extracted from {uploadedImages.length} Image(s)
                    </span>
                  </h3>

                  {/* Complete Information Matrix */}
                  {(() => {
                    const d = scanResult.declarations;
                    const nutriEntries = Object.entries(d.nutritional_values || {});

                    return (
                      <div className="space-y-4">

                        {/* Top Direct Switcher Banner to Declaration Verification */}
                        <div className="bg-gradient-to-r from-blue-950/80 to-indigo-950/80 p-3 rounded-xl border border-blue-600/40 flex items-center justify-between">
                          <div className="flex items-center space-x-2">
                            <span className="text-xl">🔍</span>
                            <div>
                              <div className="text-xs font-bold text-white">AI Declaration & Label Verification Ready</div>
                              <div className="text-[10px] text-blue-300">
                                {scanResult.declaration_analysis?.total_declarations_detected || 0} declarations analyzed across 6 dimensions.
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={() => setActiveTab("declarations")}
                            className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition shadow flex items-center space-x-1"
                          >
                            <span>Inspect Declarations</span>
                            <span>→</span>
                          </button>
                        </div>

                        {/* Grid of Core Statutory Declarations */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                          
                          {/* 1. Product & Brand */}
                          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">Commodity & Brand</span>
                            <div className="font-bold text-white text-sm mt-0.5">{scanResult.product_name}</div>
                            <div className="text-[11px] text-slate-400 font-medium">Brand: <span className="text-white">{scanResult.brand}</span></div>
                            <div className="text-[10px] text-slate-500 mt-1">Category: {scanResult.category || "Packaged Commodity"}</div>
                          </div>

                          {/* 2. Maximum Retail Price (MRP) */}
                          <div
                            onMouseEnter={() => setActiveHighlight("RULE_6_1_E")}
                            onMouseLeave={() => setActiveHighlight(null)}
                            className={`p-3 rounded-xl border transition-all ${
                              d.tax_phrase_present
                                ? "bg-slate-950 border-slate-800"
                                : "bg-red-950/40 border-red-500/50"
                            }`}
                          >
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">Maximum Retail Price (MRP)</span>
                            <div className="font-mono font-bold text-sm text-white mt-0.5">
                              {d.mrp_amount ? `₹ ${d.mrp_amount.toFixed(2)}` : "Not Declared"}
                            </div>
                            <div className={`text-[10px] mt-1 font-bold ${
                              d.tax_phrase_present ? "text-emerald-400" : "text-red-400"
                            }`}>
                              {d.tax_phrase_present ? "✓ 'Inclusive of all taxes' present" : "✕ TAX INCLUSIVITY WORDING MISSING"}
                            </div>
                            {d.unit_sale_price && (
                              <div className="text-[10px] text-slate-300 font-mono mt-0.5">USP: {d.unit_sale_price}</div>
                            )}
                          </div>

                          {/* 3. Net Quantity */}
                          <div
                            onMouseEnter={() => setActiveHighlight("RULE_6_1_C")}
                            onMouseLeave={() => setActiveHighlight(null)}
                            className={`p-3 rounded-xl border transition-all ${
                              d.is_standard_unit
                                ? "bg-slate-950 border-slate-800"
                                : "bg-red-950/40 border-red-500/50"
                            }`}
                          >
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">Net Quantity & Unit</span>
                            <div className="font-mono font-bold text-sm text-white mt-0.5">
                              {d.net_quantity_value ? `${d.net_quantity_value} ${d.net_quantity_unit}` : "Not Declared"}
                            </div>
                            <div className={`text-[10px] mt-1 font-bold ${
                              d.is_standard_unit ? "text-emerald-400" : "text-red-400"
                            }`}>
                              {d.is_standard_unit ? "✓ Standard SI Unit" : `✕ ILLEGAL NON-SI SYMBOL '${d.illegal_unit_found}'`}
                            </div>
                          </div>

                          {/* 4. Manufacturer / Packer */}
                          <div
                            onMouseEnter={() => setActiveHighlight("RULE_6_1_A")}
                            onMouseLeave={() => setActiveHighlight(null)}
                            className="bg-slate-950 p-3 rounded-xl border border-slate-800"
                          >
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">Manufacturer / Packer / Importer</span>
                            <div className="text-white font-medium mt-0.5 text-xs line-clamp-1">{d.mfr_name || "Identified on label"}</div>
                            {d.mfr_address && (
                              <div className="text-[10px] text-slate-400 mt-0.5 line-clamp-2">{d.mfr_address}</div>
                            )}
                            <div className="text-[10px] text-slate-300 mt-1 flex items-center gap-1.5">
                              <span>Postal PIN:</span>
                              <span className="font-mono text-white font-bold">{d.mfr_pin || "Not found"}</span>
                              <span className={`text-[9px] font-bold ${d.mfr_pin ? "text-emerald-400" : "text-yellow-400"}`}>
                                ({d.mfr_pin ? "✓ Verified" : "⚠ Check label"})
                              </span>
                            </div>
                          </div>

                          {/* 5. Consumer Care Coordinates */}
                          <div
                            onMouseEnter={() => setActiveHighlight("RULE_6_1_N")}
                            onMouseLeave={() => setActiveHighlight(null)}
                            className="bg-slate-950 p-3 rounded-xl border border-slate-800"
                          >
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">Consumer Grievance Redressal</span>
                            <div className="text-white text-xs font-mono mt-0.5">
                              📞 {d.consumer_care_phone || "Helpline not detected"}
                            </div>
                            <div className="text-slate-300 text-[11px] font-mono mt-0.5">
                              ✉️ {d.consumer_care_email || "Email not detected"}
                            </div>
                            <div className="text-[10px] text-slate-500 mt-1">
                              Contact: {d.consumer_care_name || "Consumer Care Cell"}
                            </div>
                          </div>

                          {/* 6. Dates, Batch & Origin */}
                          <div
                            onMouseEnter={() => setActiveHighlight("RULE_6_1_D")}
                            onMouseLeave={() => setActiveHighlight(null)}
                            className="bg-slate-950 p-3 rounded-xl border border-slate-800"
                          >
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">Dates, Batch & Origin</span>
                            <div className="text-white text-[11px] mt-0.5">
                              Mfg/Packed Date: <span className="font-mono font-bold text-white">{d.mfg_date || "N/A"}</span>
                            </div>
                            {d.expiry_date && (
                              <div className="text-slate-300 text-[10px] mt-0.5">
                                Expiry / Best Before: <span className="font-mono text-white">{d.expiry_date}</span>
                              </div>
                            )}
                            {d.batch_number && (
                              <div className="text-slate-400 text-[10px] font-mono mt-0.5">
                                Batch/Lot No: <span className="text-white font-bold">{d.batch_number}</span>
                              </div>
                            )}
                            <div className="text-slate-400 text-[10px] mt-0.5">
                              Country of Origin: <span className="text-white font-medium">{d.country_of_origin || "India"}</span>
                            </div>
                          </div>

                        </div>

                        {/* Additional Packaging Standards (FSSAI, Certifications, Vegetarian Dot) */}
                        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2">
                          <span className="text-[10px] text-slate-400 uppercase font-bold block">
                            Food Safety, Standards & Certifications
                          </span>
                          <div className="flex flex-wrap gap-2 text-xs">
                            {d.fssai_license ? (
                              <div className="bg-slate-900 border border-slate-700 px-2.5 py-1 rounded-lg flex items-center gap-1.5">
                                <span className="text-orange-400 font-bold">FSSAI:</span>
                                <span className="font-mono text-white font-bold">{d.fssai_license}</span>
                                <span className="text-emerald-400 text-[10px]">✓ 14-Digit License</span>
                              </div>
                            ) : null}

                            {d.bis_isi_mark ? (
                              <div className="bg-slate-900 border border-slate-700 px-2.5 py-1 rounded-lg flex items-center gap-1.5">
                                <span className="text-blue-400 font-bold">Standard:</span>
                                <span className="font-mono text-white">{d.bis_isi_mark}</span>
                              </div>
                            ) : null}

                            {d.vegetarian_status ? (
                              <div className="bg-slate-900 border border-slate-700 px-2.5 py-1 rounded-lg flex items-center gap-1.5">
                                <span>{d.vegetarian_status.includes("NON") ? "🟤" : "🟢"}</span>
                                <span className="text-white font-bold text-[11px]">{d.vegetarian_status}</span>
                              </div>
                            ) : null}
                          </div>
                        </div>

                        {/* Ingredients List (if present) */}
                        {d.ingredients_text && (
                          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">
                              🌿 Ingredients Declared
                            </span>
                            <p className="text-xs text-slate-200 leading-relaxed font-mono">
                              {d.ingredients_text}
                            </p>
                          </div>
                        )}

                        {/* Nutritional Information Grid (if detected) */}
                        {nutriEntries.length > 0 && (
                          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2">
                            <span className="text-[10px] text-slate-400 uppercase font-bold block">
                              🧬 Nutritional Information Table (Per Serve / 100g)
                            </span>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                              {nutriEntries.map(([k, v]) => (
                                <div key={k} className="bg-slate-900/90 border border-slate-800 rounded-lg p-2 text-center">
                                  <div className="text-[10px] text-slate-400">{k}</div>
                                  <div className="text-xs font-mono font-bold text-white mt-0.5">{v}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Active Marketing & Health Claims */}
                        {d.active_claims && d.active_claims.length > 0 && (
                          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2">
                            <span className="text-[10px] text-purple-400 uppercase font-bold block">
                              💬 Active Marketing & Health Claims (Section 15 Lab Review)
                            </span>
                            <div className="flex flex-wrap gap-2">
                              {d.active_claims.map((c, i) => (
                                <div key={i} className="bg-purple-950/50 border border-purple-600/40 rounded-lg px-2.5 py-1 text-xs text-purple-200 flex items-center gap-1.5">
                                  <span>🧪</span>
                                  <span className="font-bold">{c.claim_text}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                      </div>
                    );
                  })()}

                  {/* Violations / Action Summary */}
                  {scanResult.failed_rules > 0 && (
                    <div className="bg-red-950/40 border border-red-500/50 p-4 rounded-xl space-y-2">
                      <div className="flex items-center space-x-2 text-red-400 font-bold text-xs">
                        <span>🚨</span>
                        <span>CONTRAVENTIONS DETECTED UNDER LEGAL METROLOGY ACT, 2009</span>
                      </div>
                      <div className="space-y-1.5">
                        {scanResult.rules_evaluated
                          .filter(r => r.status === "FAIL")
                          .map((v, idx) => (
                            <div key={idx} className="bg-slate-900/90 p-2.5 rounded-lg text-xs border border-red-500/30">
                              <div className="font-bold text-red-300">{v.rule_name} ({v.legal_section})</div>
                              <div className="text-[11px] text-slate-300 mt-0.5">{v.explanation}</div>
                              <div className="text-[10px] text-red-400 font-mono mt-1">{v.penalty_clause}</div>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                </div>

              </div>

            </div>

            {/* ============================================================ */}
            {/* 4-PILLAR DETAILED AUDIT SECTION                               */}
            {/* ============================================================ */}
            <div className="space-y-3">
              <h3 className="text-sm font-extrabold text-white flex items-center gap-2 pt-2 border-t border-slate-800">
                <span>🔬</span>
                EXTENDED COMPLIANCE AUDIT (Correctness · Completeness · Placement · Readability)
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

                {/* ── PILLAR 1: CORRECTNESS ── */}
                {scanResult.correctness_audit && (() => {
                  const ca = scanResult.correctness_audit;
                  return (
                    <div className={`rounded-2xl border p-4 space-y-3 ${ca.is_fully_correct ? "bg-emerald-950/30 border-emerald-600/50" : "bg-red-950/30 border-red-500/50"}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-extrabold text-white flex items-center gap-1.5">
                          <span>✏️</span> CORRECTNESS AUDIT
                        </span>
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${ca.is_fully_correct ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"}`}>
                          {ca.is_fully_correct ? "✓ ALL CORRECT" : "✕ ERRORS FOUND"}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-300 leading-relaxed">{ca.summary}</p>
                      <div className="space-y-2">
                        {[
                          { label: "SI Unit", data: ca.units_correctness },
                          { label: "MRP Syntax", data: ca.mrp_syntax_correctness },
                          { label: "PIN Code", data: ca.pin_code_correctness },
                          { label: "Contact Format", data: ca.contact_syntax_correctness },
                          { label: "Date Format", data: ca.date_chronology_correctness },
                        ].map(({ label, data }, i) => (
                          <div key={i} className="flex items-start gap-2 text-[10px]">
                            <span className={`mt-0.5 w-3 h-3 rounded-full shrink-0 flex items-center justify-center text-[8px] font-black ${data?.is_correct ? "bg-emerald-500 text-black" : "bg-red-500 text-white"}`}>
                              {data?.is_correct ? "✓" : "✕"}
                            </span>
                            <div className="flex-1 min-w-0">
                              <span className="text-slate-400 font-bold">{label}: </span>
                              <span className="text-slate-300">{data?.detail}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}

                {/* ── PILLAR 2: COMPLETENESS ── */}
                {scanResult.completeness_audit && (() => {
                  const ca = scanResult.completeness_audit;
                  const pct = ca.overall_completeness_pct;
                  const barColor = pct >= 90 ? "bg-emerald-500" : pct >= 70 ? "bg-yellow-500" : "bg-red-500";
                  return (
                    <div className={`rounded-2xl border p-4 space-y-3 ${pct >= 90 ? "bg-emerald-950/30 border-emerald-600/50" : pct >= 70 ? "bg-yellow-950/30 border-yellow-600/50" : "bg-red-950/30 border-red-500/50"}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-extrabold text-white flex items-center gap-1.5">
                          <span>📋</span> COMPLETENESS AUDIT
                        </span>
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${pct >= 90 ? "bg-emerald-500/20 text-emerald-300" : pct >= 70 ? "bg-yellow-500/20 text-yellow-300" : "bg-red-500/20 text-red-300"}`}>
                          {pct}%
                        </span>
                      </div>

                      {/* Progress Bar */}
                      <div className="w-full bg-slate-800 rounded-full h-2">
                        <div className={`${barColor} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }}></div>
                      </div>

                      <p className="text-[11px] text-slate-300 leading-relaxed">{ca.summary}</p>

                      <div className="grid grid-cols-2 gap-1">
                        {Object.entries(ca.checklist || {}).map(([key, val], i) => (
                          <div key={i} className="flex items-center gap-1 text-[10px]">
                            <span className={val ? "text-emerald-400" : "text-red-400"}>{val ? "✓" : "✕"}</span>
                            <span className={`truncate ${val ? "text-slate-400" : "text-red-300 font-semibold"}`}>{key}</span>
                          </div>
                        ))}
                      </div>

                      {ca.missing_elements?.length > 0 && (
                        <div className="bg-red-950/50 border border-red-500/30 rounded-lg p-2 text-[10px] text-red-300">
                          <span className="font-bold">Missing Declarations: </span>
                          {ca.missing_elements.join(", ")}
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* ── PILLAR 3: PLACEMENT ── */}
                {scanResult.placement_audit && (() => {
                  const pa = scanResult.placement_audit;
                  return (
                    <div className={`rounded-2xl border p-4 space-y-3 ${pa.is_placement_compliant ? "bg-emerald-950/30 border-emerald-600/50" : "bg-red-950/30 border-red-500/50"}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-extrabold text-white flex items-center gap-1.5">
                          <span>🗂️</span> PLACEMENT AUDIT
                        </span>
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${pa.is_placement_compliant ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"}`}>
                          {pa.is_placement_compliant ? "✓ CORRECT PDP" : "✕ PLACEMENT ISSUE"}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-200 font-semibold">{pa.placement_verdict}</p>
                      <p className="text-[11px] text-slate-400 leading-relaxed">{pa.summary}</p>

                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2 text-[10px]">
                          <span className={pa.pdp_generic_name_placed ? "text-emerald-400" : "text-red-400"}>
                            {pa.pdp_generic_name_placed ? "✓" : "✕"}
                          </span>
                          <span className="text-slate-300">
                            Generic / Common Name on Principal Display Panel (PDP) — Rule 6(2)
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px]">
                          <span className={pa.pdp_net_quantity_placed ? "text-emerald-400" : "text-red-400"}>
                            {pa.pdp_net_quantity_placed ? "✓" : "✕"}
                          </span>
                          <span className="text-slate-300">
                            Net Quantity prominently placed on PDP — Rule 6(2)
                          </span>
                        </div>
                        {Object.keys(pa.panel_distribution || {}).length > 0 && (
                          <div className="mt-2 text-[10px] text-slate-500 font-mono space-y-0.5">
                            {Object.entries(pa.panel_distribution).map(([field, panel], i) => (
                              <div key={i}><span className="text-slate-400">{field}:</span> {panel}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* ── PILLAR 4: READABILITY & FONT SIZE ── */}
                {scanResult.readability_audit && (() => {
                  const ra = scanResult.readability_audit;
                  const fontOk = ra.font_size_status === "PASS";
                  return (
                    <div className={`rounded-2xl border p-4 space-y-3 ${fontOk ? "bg-emerald-950/30 border-emerald-600/50" : "bg-red-950/30 border-red-500/50"}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-extrabold text-white flex items-center gap-1.5">
                          <span>🔡</span> READABILITY & FONT SIZE
                        </span>
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${fontOk ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"}`}>
                          {fontOk ? "✓ COMPLIANT" : "✕ FONT TOO SMALL"}
                        </span>
                      </div>

                      <p className="text-[11px] text-slate-200 leading-relaxed">{ra.readability_verdict}</p>

                      <div className="space-y-2 text-[10px]">
                        {/* Font Size Row */}
                        <div className="flex items-center justify-between bg-slate-900/70 rounded-lg px-3 py-2">
                          <span className="text-slate-400">Estimated Character Height</span>
                          <span className={`font-mono font-bold ${fontOk ? "text-emerald-400" : "text-red-400"}`}>
                            ~{ra.estimated_character_height_mm} mm
                          </span>
                        </div>
                        <div className="flex items-center justify-between bg-slate-900/70 rounded-lg px-3 py-2">
                          <span className="text-slate-400">Statutory Minimum (Schedule I)</span>
                          <span className="font-mono font-bold text-white">≥ {ra.statutory_min_height_mm} mm</span>
                        </div>
                        {/* Contrast Row */}
                        <div className="flex items-center justify-between bg-slate-900/70 rounded-lg px-3 py-2">
                          <span className="text-slate-400">Contrast Ratio</span>
                          <span className="font-mono font-bold text-emerald-400">{ra.contrast_ratio}</span>
                        </div>
                        <div className="flex items-center justify-between bg-slate-900/70 rounded-lg px-3 py-2">
                          <span className="text-slate-400">Legibility Verdict</span>
                          <span className={`font-bold uppercase text-[9px] ${ra.contrast_verdict === "EXCELLENT" ? "text-emerald-400" : "text-yellow-400"}`}>
                            {ra.contrast_verdict}
                          </span>
                        </div>
                        <div className="flex items-center justify-between bg-slate-900/70 rounded-lg px-3 py-2">
                          <span className="text-slate-400">Image Blur / Sharpness Score</span>
                          <span className="font-mono font-bold text-blue-400">{ra.blur_score}/100</span>
                        </div>
                      </div>
                    </div>
                  );
                })()}

              </div>
            </div>

          </div>
        )}

        {/* ========================================================================= */}
        {/* VIEW 4: AI DECLARATION & LABEL VERIFICATION                               */}
        {/* ========================================================================= */}
        {activeTab === "declarations" && scanResult?.declaration_analysis && (() => {
          const da = scanResult.declaration_analysis;
          const statusEmoji = {
            PASS: "🟢",
            POTENTIAL_ISSUE: "🔴",
            MANUAL_REVIEW: "🟡",
          };
          const statusLabel = {
            PASS: "PASS",
            POTENTIAL_ISSUE: "POTENTIAL ISSUE",
            MANUAL_REVIEW: "MANUAL REVIEW",
          };
          const statusBg = {
            PASS: "bg-emerald-950/40 border-emerald-600/50",
            POTENTIAL_ISSUE: "bg-red-950/40 border-red-500/50",
            MANUAL_REVIEW: "bg-yellow-950/40 border-yellow-500/50",
          };
          const dimBadge = (status) => ({
            PASS: "text-emerald-400",
            POTENTIAL_ISSUE: "text-red-400",
            MANUAL_REVIEW: "text-yellow-400",
          }[status] || "text-slate-400");

          const filteredCards = da.cards.filter(c => {
            if (declarationFilter === "all") return true;
            if (declarationFilter === "issue") return c.overall_status === "POTENTIAL_ISSUE";
            if (declarationFilter === "review") return c.overall_status === "MANUAL_REVIEW";
            if (declarationFilter === "pass") return c.overall_status === "PASS";
            return true;
          });

          const typeIcon = {
            mandatory: "⚖️",
            nutritional: "🧬",
            claim: "💬",
            ingredient: "🌿",
            certification: "🏅",
          };

          return (
            <div className="space-y-5">

              {/* Page Title */}
              <div className="flex items-center justify-between pt-1">
                <div>
                  <h2 className="text-lg font-black text-white flex items-center gap-2">
                    <span>🔍</span> Declaration & Label Verification
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    AI analysis of every detected declaration and claim — correctness, completeness, readability, placement & font size.
                  </p>
                </div>
                <button
                  onClick={() => setActiveTab("result")}
                  className="bg-slate-800 text-slate-300 text-xs font-bold px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-700 transition"
                >
                  ← Back to Audit
                </button>
              </div>

              {/* Summary Banner */}
              <div className={`p-4 rounded-2xl border flex flex-col sm:flex-row gap-4 items-start sm:items-center ${statusBg[da.overall_analysis_status]}`}>
                <div className="flex items-center gap-3">
                  <span className="text-3xl">{statusEmoji[da.overall_analysis_status]}</span>
                  <div>
                    <div className="text-sm font-black text-white">
                      {statusLabel[da.overall_analysis_status]}
                    </div>
                    <p className="text-[11px] text-slate-300 mt-0.5 max-w-2xl leading-relaxed">
                      {da.summary_text}
                    </p>
                  </div>
                </div>

                {/* Stat Pills */}
                <div className="flex flex-wrap gap-2 sm:ml-auto shrink-0">
                  <div className="bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2 text-center min-w-[64px]">
                    <div className="text-lg font-black text-white font-mono">{da.total_declarations_detected}</div>
                    <div className="text-[9px] text-slate-400 uppercase font-bold">Detected</div>
                  </div>
                  <div className="bg-emerald-950/60 border border-emerald-600/40 rounded-xl px-3 py-2 text-center min-w-[64px]">
                    <div className="text-lg font-black text-emerald-400 font-mono">{da.pass_count}</div>
                    <div className="text-[9px] text-emerald-400 uppercase font-bold">🟢 Pass</div>
                  </div>
                  <div className="bg-red-950/60 border border-red-500/40 rounded-xl px-3 py-2 text-center min-w-[64px]">
                    <div className="text-lg font-black text-red-400 font-mono">{da.potential_issue_count}</div>
                    <div className="text-[9px] text-red-400 uppercase font-bold">🔴 Issues</div>
                  </div>
                  <div className="bg-yellow-950/60 border border-yellow-500/40 rounded-xl px-3 py-2 text-center min-w-[64px]">
                    <div className="text-lg font-black text-yellow-400 font-mono">{da.manual_review_count}</div>
                    <div className="text-[9px] text-yellow-400 uppercase font-bold">🟡 Review</div>
                  </div>
                </div>
              </div>

              {/* Missing Mandatory Alert */}
              {da.missing_mandatory_declarations?.length > 0 && (
                <div className="bg-red-950/50 border border-red-500/60 rounded-xl p-3 flex items-start gap-2">
                  <span className="text-lg shrink-0">🚨</span>
                  <div>
                    <div className="text-xs font-black text-red-300">MISSING MANDATORY DECLARATIONS</div>
                    <div className="text-[11px] text-red-200 mt-1">
                      {da.missing_mandatory_declarations.join(" · ")}
                    </div>
                  </div>
                </div>
              )}

              {/* Filter Bar */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] text-slate-500 font-bold uppercase">Show:</span>
                {[
                  { id: "all",    label: `All (${da.total_declarations_detected})`,     cls: "bg-slate-700 text-white" },
                  { id: "issue",  label: `🔴 Issues (${da.potential_issue_count})`,     cls: "bg-red-700 text-white" },
                  { id: "review", label: `🟡 Review (${da.manual_review_count})`,       cls: "bg-yellow-700 text-white" },
                  { id: "pass",   label: `🟢 Pass (${da.pass_count})`,                 cls: "bg-emerald-700 text-white" },
                ].map(f => (
                  <button
                    key={f.id}
                    onClick={() => setDeclarationFilter(f.id)}
                    className={`text-[10px] font-bold px-3 py-1.5 rounded-lg transition ${
                      declarationFilter === f.id
                        ? f.cls + " shadow"
                        : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {/* Declaration Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {filteredCards.map((card) => {
                  const isExpanded = expandedEvidence === card.declaration_id;
                  const overall = card.overall_status;
                  const cardBg = {
                    PASS: "bg-slate-900 border-slate-800",
                    POTENTIAL_ISSUE: "bg-red-950/30 border-red-500/40",
                    MANUAL_REVIEW: "bg-yellow-950/20 border-yellow-600/40",
                  }[overall] || "bg-slate-900 border-slate-800";

                  const dims = [
                    { label: "Presence",     dim: card.presence },
                    { label: "Completeness", dim: card.completeness },
                    { label: "Correctness",  dim: card.correctness },
                    { label: "Readability",  dim: card.readability },
                    { label: "Placement",    dim: card.placement },
                    { label: "Font Size",    dim: card.font_size },
                  ];

                  return (
                    <div key={card.declaration_id} className={`rounded-2xl border ${cardBg} flex flex-col overflow-hidden transition-all`}>

                      {/* Card Header */}
                      <div className="p-4 space-y-1">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="text-base shrink-0">{typeIcon[card.declaration_type] || "📄"}</span>
                            <div className="min-w-0">
                              <div className="text-xs font-extrabold text-white leading-tight truncate">{card.label}</div>
                              <div className="text-[10px] text-slate-500 font-mono">{card.declaration_type.toUpperCase()} • {card.panel_found_on}</div>
                            </div>
                          </div>
                          <span className={`text-[10px] font-mono font-black px-2 py-1 rounded-lg shrink-0 ${
                            overall === "PASS" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" :
                            overall === "POTENTIAL_ISSUE" ? "bg-red-500/20 text-red-300 border border-red-500/30" :
                            "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30"
                          }`}>
                            {statusEmoji[overall]}
                          </span>
                        </div>

                        {/* Detected Value */}
                        <div className="font-mono text-sm font-bold text-white bg-slate-950/80 rounded-lg px-3 py-2 mt-2 border border-slate-800 leading-snug break-all">
                          {card.detected_value}
                        </div>
                      </div>

                      {/* 6-Dimension Grid */}
                      <div className="px-4 pb-3 grid grid-cols-2 gap-x-4 gap-y-1">
                        {dims.map(({ label, dim }) => (
                          <div key={label} className="flex items-center gap-1.5 text-[10px]" title={dim.detail}>
                            <span className={`font-black ${dimBadge(dim.status)}`}>
                              {dim.status === "PASS" ? "✓" : dim.status === "POTENTIAL_ISSUE" ? "✕" : "⚠"}
                            </span>
                            <span className="text-slate-400 font-medium">{label}</span>
                          </div>
                        ))}
                      </div>

                      {/* Flag Reason */}
                      {card.flag_reason && (
                        <div className="mx-4 mb-3 bg-slate-950/60 border border-slate-700 rounded-lg px-3 py-2 text-[10px] text-slate-300 leading-relaxed">
                          {card.flag_reason}
                        </div>
                      )}

                      {/* Evidence Toggle */}
                      <div className="border-t border-slate-800 px-4 py-2.5">
                        <button
                          onClick={() => setExpandedEvidence(isExpanded ? null : card.declaration_id)}
                          className="w-full text-[11px] font-bold text-blue-400 hover:text-blue-300 flex items-center justify-between transition"
                        >
                          <span>🔎 View Evidence & Details</span>
                          <span className="text-slate-500">{isExpanded ? "▲" : "▼"}</span>
                        </button>
                      </div>

                      {/* Expanded Evidence Drawer */}
                      {isExpanded && (
                        <div className="border-t border-slate-800 bg-slate-950/70 p-4 space-y-3 text-[10px]">

                          {/* Per-Dimension Details */}
                          <div className="space-y-2">
                            {dims.map(({ label, dim }) => (
                              <div key={label} className="space-y-0.5">
                                <div className="flex items-center gap-1.5">
                                  <span className={`font-black text-[11px] ${dimBadge(dim.status)}`}>
                                    {dim.status === "PASS" ? "✓" : dim.status === "POTENTIAL_ISSUE" ? "✕" : "⚠"}
                                  </span>
                                  <span className="font-bold text-white">{label}</span>
                                  {dim.confidence && (
                                    <span className="text-slate-500 font-mono ml-auto">conf {(dim.confidence * 100).toFixed(0)}%</span>
                                  )}
                                </div>
                                <p className="text-slate-300 leading-relaxed pl-4">{dim.detail}</p>
                                {dim.evidence_text && (
                                  <div className="pl-4 font-mono text-blue-300 bg-blue-950/30 border border-blue-800/40 rounded px-2 py-1 mt-1 break-all">
                                    "{dim.evidence_text}"
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>

                          {/* Cross-Panel Conflicts */}
                          {card.conflict_evidence?.length > 0 && (
                            <div className="bg-red-950/50 border border-red-500/40 rounded-xl p-3 space-y-2">
                              <div className="text-red-300 font-black">⚠ CROSS-PANEL CONFLICT DETECTED</div>
                              <div className="space-y-1">
                                {card.conflict_evidence.map((ev, i) => (
                                  <div key={i} className="flex items-center gap-2">
                                    <span className="text-slate-400 font-mono min-w-[80px]">{ev.panel}:</span>
                                    <span className="text-white font-mono font-bold">{ev.value}</span>
                                    {ev.context && <span className="text-slate-500">({ev.context})</span>}
                                  </div>
                                ))}
                              </div>
                              <p className="text-red-200 text-[10px] mt-1">
                                Two or more panels show different values for this declaration. Verify which is correct before issuing any notice.
                              </p>
                            </div>
                          )}

                          {/* OCR Confidence */}
                          <div className="flex items-center justify-between bg-slate-900/70 rounded-lg px-3 py-2">
                            <span className="text-slate-400">Overall OCR Confidence</span>
                            <span className={`font-mono font-bold ${card.ocr_confidence >= 0.9 ? "text-emerald-400" : card.ocr_confidence >= 0.75 ? "text-yellow-400" : "text-red-400"}`}>
                              {(card.ocr_confidence * 100).toFixed(1)}%
                            </span>
                          </div>

                          {/* Bounding Box Location */}
                          {card.bounding_box && (
                            <div className="flex items-center justify-between bg-slate-900/70 rounded-lg px-3 py-2">
                              <span className="text-slate-400">Location on Label</span>
                              <span className="font-mono text-slate-300">
                                {card.bounding_box.page_side.toUpperCase()} • x:{(card.bounding_box.x * 100).toFixed(0)}% y:{(card.bounding_box.y * 100).toFixed(0)}%
                              </span>
                            </div>
                          )}

                          {/* Important Honesty Notice for Claims */}
                          {(card.declaration_type === "claim" || card.declaration_type === "nutritional") && (
                            <div className="bg-slate-800/80 border border-slate-700 rounded-lg p-2 flex gap-2 items-start">
                              <span className="text-yellow-400 shrink-0">ℹ</span>
                              <p className="text-slate-400 leading-relaxed">
                                <b className="text-slate-300">Important:</b> OCR can read what is printed. It cannot chemically verify the actual composition, potency, or truth of this claim. A 🟡 MANUAL REVIEW status is not a legal violation — it flags that independent verification is required.
                              </p>
                            </div>
                          )}

                        </div>
                      )}

                    </div>
                  );
                })}
              </div>

              {filteredCards.length === 0 && (
                <div className="text-center py-12 text-slate-500">
                  <div className="text-3xl mb-2">🔍</div>
                  <div className="text-sm font-bold">No declarations match this filter.</div>
                </div>
              )}

            </div>
          );
        })()}

        {/* ========================================================================= */}
        {/* VIEW 5: INSPECTION HISTORY & REPOSITORY                                   */}
        {/* ========================================================================= */}
        {activeTab === "history" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <span>📁</span> Scanned Products Archive
              </h2>
              <button
                onClick={() => {
                  stopCamera();
                  setActiveTab("scan");
                }}
                className="bg-blue-600 text-white text-xs font-bold px-3 py-1.5 rounded-lg"
              >
                + Scan New Product
              </button>
            </div>

            <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
              <div className="divide-y divide-slate-800">
                {historyList.map((item, idx) => (
                  <div key={idx} className="p-4 flex items-center justify-between hover:bg-slate-850 transition">
                    <div className="space-y-0.5">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-white">{item.product_name}</span>
                        <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded font-bold uppercase ${
                          item.compliance_status === "COMPLIANT"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "bg-red-500/20 text-red-300"
                        }`}>
                          {item.compliance_status}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono">
                        {item.brand} • {item.timestamp} • Score: <b className="text-white">{item.overall_compliance_score}%</b>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => {
                          setScanResult(item);
                          setActiveTab("result");
                        }}
                        className="bg-blue-600/80 hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg text-xs font-bold"
                      >
                        View Info
                      </button>
                      <a
                        href={item.pdf_report_url || `/reports/Inspection_Report_${item.scan_id}.pdf`}
                        target="_blank"
                        className="bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg text-xs"
                      >
                        PDF
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

      </main>

      {/* Show-Cause Legal Notice Modal */}
      {noticeModalOpen && noticeData && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 bg-slate-800 border-b border-slate-700 flex items-center justify-between">
              <span className="font-bold text-xs text-white flex items-center gap-2">
                <span>⚖️</span> STATUTORY SHOW-CAUSE NOTICE (SECTION 36 & 39)
              </span>
              <button
                onClick={() => setNoticeModalOpen(false)}
                className="text-slate-400 hover:text-white font-bold"
              >
                ✕
              </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto font-mono text-xs text-slate-200 bg-slate-950 leading-relaxed whitespace-pre-wrap select-all">
              {noticeData.full_notice_text}
            </div>

            <div className="p-3 bg-slate-800 border-t border-slate-700 flex items-center justify-between">
              <span className="text-[10px] text-slate-400 font-mono">Ref: {noticeData.notice_id}</span>
              <div className="space-x-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(noticeData.full_notice_text);
                    alert("Legal notice copied!");
                  }}
                  className="bg-slate-700 text-white text-xs px-3 py-1.5 rounded-lg font-semibold"
                >
                  📋 Copy
                </button>
                <button
                  onClick={() => {
                    const printWindow = window.open("", "_blank");
                    printWindow.document.write(`<pre style="font-family: monospace; font-size: 12px; padding: 20px;">${noticeData.full_notice_text}</pre>`);
                    printWindow.document.close();
                    printWindow.print();
                  }}
                  className="bg-blue-600 text-white text-xs px-4 py-1.5 rounded-lg font-bold"
                >
                  🖨️ Print
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Clean Footer */}
      <footer className="bg-slate-950 border-t border-slate-900 py-3 text-center text-xs text-slate-500">
        Legal Metrology Product Scanner • Packaged Commodities Rules, 2011 & Legal Metrology Act, 2009
      </footer>

    </div>
  );
}

// Render Root
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<LegalMetrologySimpleApp />);
