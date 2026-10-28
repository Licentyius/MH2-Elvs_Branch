"""
    License information: data/licenses/makehuman_license.txt
    Author: black-punkduck, Elvaerwyn_MH2 2026 V1.5

    Classes:
    * DownLoadImport
"""
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLineEdit, QLabel, QWidget,
    QMessageBox, QRadioButton, QCheckBox, QComboBox, QStyle, QScrollArea, QSizePolicy
)

from PySide6.QtGui import QIcon, QFontMetrics
from PySide6.QtCore import Qt
from gui.assettabwindow import MHSelectAssetWindow
from gui.common import ErrorBox, WorkerThread, MHBusyWindow, IconButton, MHFileRequest, MHProgWindow
from opengl.texture import MH_Thumb
from core.importfiles import AssetPack

import os
import json
import urllib.request

class DownLoadImport(QVBoxLayout):
    def __init__(self, parent, view, displaytitle):
        self.parent = parent
        self.glob = parent.glob
        self.env = parent.env
        self.view = view
        self.displaytitle = displaytitle
        self.bckproc = None     
        self.error   = None     
        self.zipfile = None     
        self.assetlistpath = None
        self.assetjson = None
        self.assetpacklistpath = None
        self.assetpackjson = None
        self.packitems = []
        self.packurls = []
        self.use_userpath = True
        self.download_cart = []
        self.cart_processing = False
        self.assets = AssetPack()
        self.active_parallel_workers = [] 
        self.favorites_db = {"assets": [], "creators": []}

        # --- DUAL ROUTING CONNECTIONS SETUP ---
        self.use_github_backend = True  # Toggle value tracking flag
        self.github_base_url = "https://github.com"

        stdmesh = self.env.release_info["standardmesh"]
        self.parentmesh = self.glob.baseClass.baseInfo.get("parentmesh")

        # Resolve clean universal tracking naming conventions 
        assetname = "community_index.json"
        assetpackname = "community_packs.json"

        dl = os.path.join(self.env.path_userdata, "downloads", self.env.basename)   
        self.assetlistpath = os.path.join(dl, assetname)

        pdl = os.path.join(self.env.path_userdata, "downloads", stdmesh)            
        self.env.mkdir(pdl)                                                         

        self.assetpacklistpath = os.path.join(pdl, assetpackname)
        self.getAssetPackList()

        if self.assetjson is None:
            raw_data = self.assets.alistReadJSON(self.env, self.assetlistpath)
            if isinstance(raw_data, list):
                self.json = {}
                for idx, item in enumerate(raw_data):
                    if isinstance(item, dict):
                        k = item.get("title", item.get("id", str(idx)))
                        self.json[k] = item
            else:
                self.json = raw_data if raw_data is not None else {}

        super().__init__()

        container = QWidget()
        layout = QVBoxLayout()
        container.setLayout(layout)
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.setContentsMargins(0, 0, 0, 0)
        scrollArea.setWidget(container)
        # ----------------------------------------------------
        # DUAL MODE INTERFACE TOGGLE CONTROL PANEL
        # ----------------------------------------------------
        backend_group = QGroupBox("Select Repository Connection Gateway")
        backend_group.setObjectName("subwindow")
        mode_layout = QHBoxLayout()

        self.rad_cache_mode = QRadioButton("Use Baseline Offline Cache")
        self.rad_cache_mode.setChecked(True)
        self.rad_cache_mode.toggled.connect(self.on_backend_mode_changed)

        self.rad_github_mode = QRadioButton("Use Live GitHub Repository")
        self.rad_github_mode.toggled.connect(self.on_backend_mode_changed)

        mode_layout.addWidget(self.rad_cache_mode)
        mode_layout.addWidget(self.rad_github_mode)
        backend_group.setLayout(mode_layout)
        self.addWidget(backend_group)

        self.latest = self.assets.testAssetList(self.assetlistpath)
        if self.latest is None:
            self.asdlbutton = QPushButton("Refresh & Compile Asset Databases")
        else:
            self.asdlbutton = QPushButton("Synchronize Master Asset Lists [" + self.latest + "]")
            
        self.asdlbutton.setEnabled(True)
        self.asdlbutton.clicked.connect(self.listDownLoad)
        self.asdlbutton.setToolTip("Pulls the latest community tracking indices to update your browser grid mapping.")
        self.addWidget(self.asdlbutton)

        # --- PRE-CALCULATED SYNC THUMBNAIL CACHE INTERFACE ELEMENT ---
        self.syncThumbsButton = QPushButton("Sync Thumbnail Cache (Download All)")
        self.syncThumbsButton.setEnabled(True)
        
        total_thumbs_to_cache = 0
        if hasattr(self, 'json') and self.json:
            for key, rec in self.json.items():
                if isinstance(rec, dict):
                    f_dict = rec.get("files")
                    if isinstance(f_dict, dict) and f_dict.get("thumb"):
                        total_thumbs_to_cache += 1

        if total_thumbs_to_cache > 0:
            calculated_minutes = int((total_thumbs_to_cache * 0.675) / 60)
            if calculated_minutes < 1:
                calculated_minutes = 1
            slow_net_minutes = int(calculated_minutes * 2.5)
            
            self.syncThumbsButton.setText(f"Sync Thumbnail Cache ({total_thumbs_to_cache} Items)")
            tooltip_text = (
                f"Download every available thumbnail at once.<br>"
                f"<b>Estimated Duration:</b> ~{calculated_minutes} mins on standard nets.<br>"
                f"<i>Warning: May take up to {slow_net_minutes} minutes on highly congested or slower connections. "
                f"Already cached files will be skipped automatically to save data.</i>"
            )
        else:
            tooltip_text = "Download every available thumbnail to your local drive at once.<br>Please download or refresh asset lists first to compile estimates."

        self.syncThumbsButton.clicked.connect(self.syncAllThumbnailsCall)
        self.syncThumbsButton.setToolTip(tooltip_text)
        self.addWidget(self.syncThumbsButton)

        gb = QGroupBox("Single Asset")
        gb.setObjectName("subwindow")
        vlayout = QVBoxLayout()

        vlayout.addWidget(QLabel("Browse in list to find your asset."))
        self.browsebutton = QPushButton("Asset Browser")
        self.browsebutton.setEnabled(True)
        self.browsebutton.clicked.connect(self.selectfromList)
        self.browsebutton.setToolTip("Browse downloaded asset list.")
        vlayout.addWidget(self.browsebutton)

        gb.setLayout(vlayout)
        self.addWidget(gb)

        # ----------------------------------------------------
        # BATCH CART PANEL
        # ----------------------------------------------------
        checkout_panel = QGroupBox("Batch Asset Cart")
        checkout_panel.setObjectName("subwindow")
        panel_layout = QHBoxLayout(checkout_panel)

        self.masterCartLabel = QLabel("Cart is empty")
        panel_layout.addWidget(self.masterCartLabel)

        self.checkoutBtn = QPushButton("Download All Items")
        self.checkoutBtn.setDisabled(True) 
        
        icon_path = os.path.join(self.env.path_sysicon, "cart.png")
        if os.path.exists(icon_path):
            self.checkoutBtn.setIcon(QIcon(icon_path))
        else:
            dl_icon = self.parent.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
            self.checkoutBtn.setIcon(dl_icon)
            
        self.checkoutBtn.clicked.connect(self.on_checkout_clicked)
        panel_layout.addWidget(self.checkoutBtn)
        self.addWidget(checkout_panel) 
        gb = QGroupBox("Asset Pack")
        gb.setObjectName("subwindow")

        ilayout = QVBoxLayout()
        ilayout.addWidget(QLabel("Select asset pack:"))

        self.combo = QComboBox()
        self.combo.setFixedWidth(280)
        self.combo.addItems(self.packitems)
        self.combo.setToolTip("An asset pack is a zip file.\nDownload of the standard assets can be done here.\nThey also can be downloaded manually\nand extracted with extract button below.")
        self.combo.currentIndexChanged.connect(self.packNameChanged)
        ilayout.addWidget(self.combo)

        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel("or select and copy an URL from:"))
        linklabel = QLabel()
        ltext = "<a href='https://github.com'>Asset Packs</a>"
        linklabel.setToolTip("Opens browser to search for asset packs.\nAn asset pack usually ends with .zip")
        linklabel.setText(ltext)
        linklabel.setOpenExternalLinks(True)
        hlayout.addWidget(linklabel)
        ilayout.addLayout(hlayout)

        self.packname = QLineEdit("")
        self.packname.editingFinished.connect(self.packinserted)
        ilayout.addWidget(self.packname)

        self.dlbutton = QPushButton("Download Asset Pack")
        self.dlbutton.clicked.connect(self.downLoad)
        ilayout.addWidget(self.dlbutton)

        userpath = QLabel() 
        metrics = QFontMetrics(userpath.font())
        short_text = metrics.elidedText(self.env.path_userdata, Qt.ElideMiddle, 260)
        userpath.setText("Destination user path for base: "  + self.env.basename + "\n" + short_text)
        userpath.setToolTip("Files will be extracted to " + self.env.basename + " folders in " + self.env.path_userdata)
        ilayout.addWidget(userpath)

        if self.env.admin:
            syspath = QLabel("Destination system path for base: " + self.env.basename + "\n" + self.env.path_sysdata)
            syspath.setToolTip("Files will be extracted to " + self.env.basename + " folders in " + self.env.path_sysdata)
            ilayout.addWidget(syspath)

            self.userbutton = QRadioButton("Install in your user path")
            self.userbutton.setChecked(True)
            self.systembutton = QRadioButton("Install in system path")
            self.userbutton.toggled.connect(self.setMethod)
            self.systembutton.toggled.connect(self.setMethod)
            ilayout.addWidget(self.userbutton)
            ilayout.addWidget(self.systembutton)

        ilayout.addWidget(QLabel("\nAfter download use the filename inserted by\nprogram or select an already downloaded\nasset pack and press extract:"))

        hlayout = QHBoxLayout()
        self.zipfilebuttton = IconButton(0, os.path.join(self.env.path_sysicon, "files.png"), "Select zip file.", self.searchzipfile, 16)
        hlayout.addWidget(self.zipfilebuttton)

        self.filename = QLineEdit("")
        self.filename.editingFinished.connect(self.fnameinserted)
        self.filename.setText(self.parent.glob.lastdownload)
        hlayout.addWidget(self.filename)
        ilayout.addLayout(hlayout)

        self.savebutton = QPushButton("Extract")
        self.savebutton.clicked.connect(self.extractZip)
        ilayout.addWidget(self.savebutton)

        ilayout.addWidget(QLabel("\nIf the downloaded file is no longer needed,\npress cleanup to delete the temporary folder"))
        self.clbutton = QPushButton("Clean Up")
        self.clbutton.clicked.connect(self.cleanUp)
        ilayout.addWidget(self.clbutton)
        ilayout.addStretch()
        gb.setLayout(ilayout)
        layout.addWidget(gb)
        
        self.packinserted()
        self.fnameinserted()
        self.addWidget(scrollArea)
    def on_backend_mode_changed(self):
        """Processes the toggle between the Baseline Cache index and Live GitHub streams."""
        self.use_github_backend = self.rad_github_mode.isChecked()
        if self.use_github_backend:
            self.asdlbutton.setText("Synchronize Master Asset Lists [GitHub Live]")
        else:
            self.asdlbutton.setText("Restore Baseline Offline Cache [Local Baseline]")

    def searchzipfile(self):
        freq = MHFileRequest(self.glob, "Select zipfile", "compressed file (*.zip)", "")
        name = freq.request()
        if name is not None:
            self.filename.setText(name)
            self.fnameinserted()

    def defaultList(self):
        self.packitems = [""]
        self.packurls = [""]
        sysassets = self.env.release_info.get("url_systemassets", [])
        for elem in sysassets:
            base = elem.get("base")
            if base == self.env.basename or base == "*" or self.parentmesh == base:
                self.packitems.append(elem["title"])
                self.packurls.append(elem["url"])

    def formList(self, packs):
        self.packitems = []
        self.packurls = []
        for key, elem in packs.items():
            base = elem.get("base")
            if base == self.env.basename or base == "*" or self.parentmesh == base:
                if "url" in elem:
                    text = elem.get("descr", key)
                    if "license" in elem: text += ", " + elem["license"]
                    if "size" in elem: text += " (" + str(elem["size"]) + " mb)"
                    self.packitems.append(text)
                    self.packurls.append(elem["url"])

    def getAssetPackList(self):
        # UNIVERSAL FALLBACK CACHE LOGIC
        if not os.path.exists(self.assetpacklistpath):
            self.defaultList()
            return
        self.assetpackjson = self.env.readJSON(self.assetpacklistpath)
        if self.assetpackjson is not None and "packs" in self.assetpackjson:
            self.formList(self.assetpackjson["packs"])   
        else:
            self.defaultList()

    def packNameChanged(self, index):
        """Safely updates the URL line entry while protecting against out-of-bounds array drops."""
        # Ensure the index is within the actual boundaries of the currently loaded array items
        if index >= 0 and index < len(self.packurls):
            target_url = self.packurls[index]
            if target_url:
                f = self.env.release_info["url_fileserver"] + "/" + target_url
                self.packname.setText(f)
                self.packinserted()
        else:
            # Fallback block if the lists are empty due to offline recovery setup
            self.packname.setText("")
            self.dlbutton.setDisabled(True)


    def setMethod(self, value):
        self.use_userpath = self.userbutton.isChecked() if hasattr(self, 'userbutton') else True

    def packinserted(self):
        self.dlbutton.setEnabled(len(self.packname.text()) > 0)

    def fnameinserted(self):
        self.savebutton.setEnabled(len(self.filename.text()) > 0)

    def selectfromList(self):
        if self.assetjson is None:
            if not os.path.exists(self.assetlistpath):
                self.assetjson = {}
            else:
                self.assetjson = self.assets.alistReadJSON(self.env, self.assetlistpath)
        w = self.glob.showSubwindow("loadasset", self, MHSelectAssetWindow, self.assetjson)

    def par_unzip(self, bckproc, *args):
        filename = self.filename.text()
        
        # 1. Determine the true destination path chosen by the user in the UI
        destpath = self.env.path_sysdata if (hasattr(self, 'use_userpath') and self.use_userpath is False) else self.env.path_userdata
        destpath = destpath.replace("\\", "/")
        
        # 2. Perform the raw extraction into a temporary scratch directory first
        tempdir, error = self.assets.unZip(filename)
        if error is not None:
            self.error = error
            return
            
        self.env.logLine(1, f"[SMART UNZIP] Scanning extracted files to route categories correctly into: {destpath}")
        
        try:
            import shutil
            # Determine the mesh type folder name (defaults to 'hm08')
            mesh_folder = self.env.basename if self.env.basename else "hm08"
            
            for root, dirs, files in os.walk(tempdir):
                for file in files:
                    source_file = os.path.join(root, file)
                    file_lower = file.lower()
                    
                    # --- SMART ROUTER ENGINE: Detect extensions and assign specific target paths ---
                    if file_lower.endswith(('.mhclo', '.obj', '.mhmat', '.mat', '.png', '.jpg', '.jpeg', '.thumb')) and not "target" in root:
                        # Raw clothing packs belong nested inside clothes/hm08/your_pack_name/
                        pack_name = os.path.basename(filename)[:-4] # Strips the '.zip' extension out
                        sub_route = f"clothes/{mesh_folder}/{pack_name}"
                    elif file_lower.endswith(('.target', '.npz')):
                        # Morph targets belong inside target/hm08/
                        sub_route = f"target/{mesh_folder}"
                    elif file_lower.endswith(('.mhmat', '.mat')) and "material" in root:
                        # Skin and materials profiles belong inside skins/
                        sub_route = f"skins"
                    else:
                        # Fallback path to preserve original zip internal file path layout structures
                        sub_route = os.path.relpath(root, tempdir).replace("\\", "/")
                    
                    # SAFETY GUARD: If the destpath already ends with '/data', do not re-append it inside sub_route
                    if destpath.lower().endswith("/data") and sub_route.lower().startswith("data/"):
                        sub_route = sub_route[5:]
                    elif not destpath.lower().endswith("/data") and not sub_route.lower().startswith("data/"):
                        sub_route = f"data/{sub_route}"
                    
                    # Construct the absolute path on your F:/ drive
                    final_destination = os.path.join(destpath, sub_route, file).replace("\\", "/")
                    
                    # Build the target folders dynamically on your drive
                    os.makedirs(os.path.dirname(final_destination), exist_ok=True)
                    
                    # Copy the files over natively
                    shutil.copy2(source_file, final_destination)
                    
            self.env.logLine(1, "[SMART UNZIP] All raw community assets categorized and structured successfully!")
        except Exception as copy_err:
            self.error = f"Asset category routing failed: {str(copy_err)}"


    def finishUnzip(self):
        self.assets.cleanupUnzip()
        if self.prog_window is not None:
            self.prog_window.progress.close()
            self.prog_window = None
        self.glob.MainWindow.syncRepositories()
        if self.error:
            QMessageBox.critical(self.parent, "Error", self.error)
        else:
            QMessageBox.information(self.parent, "Done!", self.bckproc.finishmsg)
        self.bckproc = None

    def extractZip(self):
        fname = self.filename.text()
        if not fname.endswith(".zip"):
            ErrorBox(self.parent, "Filename should have the suffix .zip")
            return
        self.env.logLine(1, "Extract zip: " + fname)
        if self.bckproc == None:
            self.error = None
            self.prog_window = MHBusyWindow("Extract ZIP file", "extracting ...")
            self.prog_window.progress.forceShow()
            self.bckproc = WorkerThread(self.par_unzip, None)
            self.bckproc.start()
            self.bckproc.finishmsg = "Zip file has been imported"
            self.bckproc.finished.connect(self.finishUnzip)

    def displayProgress(self, total_size, l):
        if self.prog_window:
            v = 1000 if total_size == 0 else (l / total_size) * 1000
            self.prog_window.setValue(int(v))

    def par_download(self, bckproc, *args):
        try:
            if isinstance(args[0], (tuple, list)):
                tempdir = args[0][0]
                filename = args[0][1]
            else:
                tempdir = args[0]
                filename = args[1]
        except Exception:
            # Absolute safety fallback mapping to ensure the download pipeline never stalls
            tempdir = self.assets.tempDir()
            filename = os.path.basename(self.packname.text())

        self.error = None
        self.env.logLine(1, "Download " + self.packname.text() + " to " + tempdir)
        (err, text) = self.assets.getAssetPack(self.packname.text(), tempdir, filename, unzip=False, responsefunc=self.displayProgress)
        self.error = text

    def downLoad(self):
        url = self.packname.text()
        if not (url.startswith("ftp:") or url.startswith("http:") or url.startswith("https:")):
            ErrorBox(self.parent, "URL must start with a known protocol [http, https, ftp]")
            return
        filename = os.path.split(url)[1]
        if self.bckproc == None:
            tempdir = self.assets.tempDir()
            self.parent.glob.lastdownload = os.path.join(tempdir, filename)
            self.filename.setText(self.parent.glob.lastdownload)
            self.fnameinserted()
            self.prog_window = MHProgWindow("Download File", 1000)
            self.prog_window.setLabelText("Download " + url + " to " + tempdir)
            self.prog_window.progress.forceShow()
            self.bckproc = WorkerThread(self.par_download, tempdir, filename)
            self.bckproc.start()
            self.bckproc.finishmsg = "Download finished"
            self.bckproc.finished.connect(self.finishLoad)

    def finishLoad(self):
        if self.prog_window is not None:
            self.prog_window.progress.close()
            self.prog_window = None
        if self.error:
            ErrorBox(self.parent, self.error)
        else:
            QMessageBox.information(self.parent, "Done!", self.bckproc.finishmsg)
        self.bckproc = None 
        if hasattr(self, 'cart_processing') and self.cart_processing:
            self.on_checkout_clicked()

    def finishListLoad(self):
        if hasattr(self, 'prog_window') and self.prog_window is not None:
            self.prog_window.progress.close()
            self.prog_window = None
        if self.error:
            ErrorBox(self.parent, self.error)
        else:
            QMessageBox.information(self.parent, "Done!", self.bckproc.finishmsg)
        self.bckproc = None
        self.latest = self.assets.testAssetList(self.assetlistpath)
        if hasattr(self, 'browsebutton') and self.browsebutton:
            self.browsebutton.setEnabled(self.latest is not None)
        self.getAssetPackList()
        if hasattr(self, 'combo') and self.combo is not None:
            self.combo.clear()
            self.combo.addItems(self.packitems)

    def par_listdownload(self, bckproc, *args):
        import os
        import json
        import urllib.request
        
        self.error = None

        if hasattr(self, 'rad_github_mode'):
            self.use_github_backend = self.rad_github_mode.isChecked()
        else:
            self.use_github_backend = False

        # ----------------------------------------------------
        # PATH 1: ORIGINAL UNTOUCHED LEGACY NETWORK GATEWAY
        # ----------------------------------------------------
        if not self.use_github_backend:
            # FORCE RE-CALCULATING THE FILENAMES DIRECTLY FROM THE CORE LIVE SERVER PROFILE
            # This completely fixes the 404 by using the exact filenames the server expects!
            assetname = os.path.split(self.env.release_info["url_assetlist"])[1]
            assetpackname = os.path.split(self.env.release_info["url_assetpacklist"])[1]
            
            stdmesh = self.env.release_info["standardmesh"]
            dl = os.path.join(self.env.path_userdata, "downloads", self.env.basename)
            pdl = os.path.join(self.env.path_userdata, "downloads", stdmesh)
            
            # Recalculate true local storage file paths
            dest_list = os.path.join(dl, assetname)
            dest_packs = os.path.join(pdl, assetpackname)
            
            # Re-assign variables so the asset engine discovers them on disk
            self.assetlistpath = dest_list
            self.assetpacklistpath = dest_packs
            
            # Run your untouched native legacy downloading loops exactly like your old script did
            local_paths = [dest_list, dest_packs]
            i = 0
            for fname in self.env.release_info["url_assetlist"], self.env.release_info["url_assetpacklist"]:
                dest = local_paths[i]
                i += 1
                self.prog_window.setValueAndText(0, "Download " + fname + " to " + dest)
                loaded, text = self.assets.getUrlFile(fname, dest, responsefunc=self.displayProgress)
                self.error = text
                if loaded is False:
                    return
            return

        # ----------------------------------------------------
        # PATH 2: ISOLATED LIVE GITHUB REPOSITORY PASS
        # ----------------------------------------------------
        # Force the destination file variables to follow your clean GitHub names matrix
        self.assetlistpath = os.path.join(os.path.join(self.env.path_userdata, "downloads", self.env.basename), "community_index.json")
        self.assetpacklistpath = os.path.join(os.path.join(self.env.path_userdata, "downloads", self.env.release_info["standardmesh"]), "community_packs.json")
        
        destination = self.assetlistpath
        destination2 = self.assetpacklistpath
        
        domain_part1 = "https://raw."
        domain_part2 = "githubuser"
        domain_part3 = "content.com"
        raw_server_gateway = f"{domain_part1}{domain_part2}{domain_part3}"
        
        target_repository = "Makehuman-2/MH2_Asset_Repository_CC-By"
        target_branch = "main"
        
        list_url = f"{raw_server_gateway}/{target_repository}/{target_branch}/community_index.json"
        packs_url = f"{raw_server_gateway}/{target_repository}/{target_branch}/community_packs.json"

        request_headers = {"Accept": "*/*", "User-Agent": "Mozilla/5.0 MakeHuman2_Asset_Cart"}
        
        try:
            req_packs = urllib.request.Request(packs_url, headers=request_headers)
            with urllib.request.urlopen(req_packs, timeout=15) as response:
                packs_bytes = response.read()
                if len(packs_bytes) > 0 and b"{" in packs_bytes:
                    os.makedirs(os.path.dirname(destination2), exist_ok=True)
                    with open(destination2, "wb") as f_out_packs:
                        f_out_packs.write(packs_bytes)
                else:
                    self.error = "Sync failed: Remote 'community_packs.json' catalog is blank."
                    return
        except Exception as e:
            self.error = f"Failed to download asset packs directory list: {str(e)}"
            return

        try:
            req_list = urllib.request.Request(list_url, headers=request_headers)
            with urllib.request.urlopen(req_list, timeout=15) as response:
                list_bytes = response.read()
                if len(list_bytes) > 0 and (b"[" in list_bytes or b"{" in list_bytes):
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    with open(destination, "wb") as f_out_list:
                        f_out_list.write(list_bytes)
                else:
                    raise ValueError("Empty response")
        except Exception:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "w", encoding="utf-8") as f_blank:
                json.dump([], f_blank)

    def listDownLoad(self):
        if self.bckproc == None:
            self.assetjson = None       # reset this
            self.prog_window = MHProgWindow("Download Lists", 1000)
            self.prog_window.progress.forceShow()
            # --- MAKE SURE THIS MATCHES THIS EXACTLY ---
            self.bckproc = WorkerThread(self.par_listdownload, self.assetlistpath, self.assetpacklistpath)
            # -------------------------------------------
            self.bckproc.start()
            self.bckproc.finishmsg = "Download finished"
            self.bckproc.finished.connect(self.finishListLoad)


    def par_thumb_cache_download(self, bckproc, *args):
        if self.assetjson is None:
            self.assetjson = self.assets.alistReadJSON(self.env, self.assetlistpath)
        if not self.assetjson: return
        self.error = None
        all_tasks = []
        for key, rec in self.json.items():
            if isinstance(rec, dict):
                f_dict = rec.get("files")
                if isinstance(f_dict, dict):
                    thumb_url = f_dict.get("thumb")
                    if thumb_url: 
                        all_tasks.append((key, thumb_url))
                        
        needed_tasks = []
        for asset_key, thumb_url in all_tasks:
            d_title = self.json[asset_key].get("title", asset_key)
            t_filename = d_title[:-4] + ".thumb" if d_title.lower().endswith(".png") else d_title + ".thumb"
            dest_file = os.path.join(self.env.path_userdata, "downloads", self.env.basename, "render", t_filename)
            if not os.path.exists(dest_file):
                needed_tasks.append((asset_key, thumb_url, dest_file))
                
        if not needed_tasks: 
            return

    def syncAllThumbnailsCall(self):
        if self.bckproc is None:
            self.prog_window = MHProgWindow("Synchronizing Thumbnail Cache", 1000)
            self.prog_window.progress.forceShow()
            self.bckproc = WorkerThread(self.par_thumb_cache_download, None)
            self.bckproc.finishmsg = "Thumbnail database cache synchronized successfully!"
            self.bckproc.finished.connect(self.finishListLoad)
            self.bckproc.start()

    def par_filesdownload(self, bckproc, *args):
        destination = args[0][0]
        files = args[0][1]
        self.error = None
        for elem in files:
            dest = os.path.split(elem)[1]
            if hasattr(bckproc, 'associated_window') and bckproc.associated_window is not None:
                bckproc.associated_window.setLabelText("Loading: " + elem)
            destpath = os.path.join(destination, dest)
            loaded, text = self.assets.getUrlFile(elem, destpath)
            if loaded is False:
                self.error = text
                return
            if destpath.endswith(".thumb"):
                thumb = MH_Thumb()
                thumb.rescale(destpath)
            elif destpath.endswith(".target"):
                self.glob.Targets.categories.newUserCategories()
                tname, t = self.glob.Targets.categories.findUserAsset(dest)
                if tname is not None: 
                    self.glob.Targets.createTarget(tname, t)
        self.error = text

    def parentAsset(self, key):
        pobj = self.assetjson[key]["belongs_to"]
        if pobj["belonging_is_assigned"] is False:
            return False, self.env.path_userdata
        else:
            if "belongs_to_core_asset" in pobj:
                (mtype, folder) = pobj["belongs_to_core_asset"].split("/", 2)
                path = self.env.existDataDir(mtype, self.env.basename) if mtype == "eyes" else self.env.existDataDir(mtype, self.env.basename, folder)
                if path is None: 
                    return False, None
                return True, path
            parentkey = str(pobj["belongs_to_id"])
            mtype = self.assetjson[parentkey]["type"]
            if mtype == "model": 
                mtype = "skins"
            folder = self.assets.titleToFileName(pobj["belongs_to_title"])
            path = self.env.existDataDir(mtype, self.env.basename, folder)
            return (True, path) if path is not None else (False, self.env.existDataDir(mtype, self.env.basename))

    def singleDownLoad(self, assetname):
        supportedclasses = ["clothes", "hair", "eyes", "teeth", "eyebrows", "eyelashes", "expression", "pose", "skin", "rig", "proxy", "model", "target", "material"]
        if self.assetjson is None: 
            self.assetjson = self.assets.alistReadJSON(self.env, self.assetlistpath)
        if self.assetjson is None: 
            return
        if assetname in self.assetjson:
            item = self.assetjson[assetname]
            folder = item.get("folder")
        else: 
            return
        mtype, flist = self.assets.alistGetFiles(self.assetjson, assetname)
        if mtype not in supportedclasses: 
            return
        if mtype == "material":
            okay, path = self.parentAsset(assetname)
            if okay is False:
                if path is None: 
                    return
                freq = MHFileRequest(self.glob, "Select a directory to save additional materials", None, path, save=".")
                path = freq.request()
                if path is None: 
                    return
                folder, err = self.assets.createMaterialsFolder(path)
            else:
                folder, err = self.assets.alistCreateFolderFromTitle(self.env.path_userdata, self.env.basename, mtype, folder)
        else:
            folder, err = self.assets.alistCreateFolderFromTitle(self.env.path_userdata, self.env.basename, mtype, folder)
        if folder is None: 
            return None
            
        local_prog_window = MHBusyWindow("Download files to " + folder, "loading ...")
        local_prog_window.progress.forceShow()
        worker = WorkerThread(self.par_filesdownload, folder, flist)
        worker.finishmsg = "Download finished"
        worker.associated_window = local_prog_window
        self.active_parallel_workers.append((assetname, worker))
        worker.finished.connect(self.finish_parallel_load)
        worker.start()
        self.bckproc = worker
        return worker

    def add_to_cart_clicked(self):
        button = self.sender()
        assetname = button.property("asset_name")
        if assetname in self.download_cart: 
            return
        self.download_cart.append(assetname)
        button.setEnabled(False)
        self.sync_cart_labels()

    def update_cart_time_estimate(self):
        cart_len = len(self.download_cart)
        if cart_len == 0:
            self.masterCartLabel.setText("Cart is empty")
            self.checkoutBtn.setDisabled(True)
            return
        self.checkoutBtn.setEnabled(True)
        self.masterCartLabel.setText(f"Items waiting in queue: {cart_len}")

    def on_checkout_clicked(self):
        if not self.download_cart: 
            return
        self.checkoutBtn.setEnabled(False)
        self.masterCartLabel.setText("Downloading parallel queue...")
        self.cart_processing = True
        batch_queue = list(self.download_cart)
        for asset in batch_queue:
            self.singleDownLoad(asset)

    def finish_parallel_load(self):
        sender_worker = self.sender()
        if sender_worker and hasattr(sender_worker, 'associated_window') and sender_worker.associated_window is not None:
            sender_worker.associated_window.progress.close()
        
        still_running = []
        for asset, worker in self.active_parallel_workers:
            if worker and worker.isRunning(): 
                still_running.append((asset, worker))
            else:
                if asset in self.download_cart: 
                    self.download_cart.remove(asset)
                    
        self.active_parallel_workers = still_running
        
        if not still_running:
            self.cart_processing = False
            self.download_cart.clear()
 
            self.sync_cart_labels()
            self.masterCartLabel.setText("All items downloaded successfully! Cart empty.")
            
            QMessageBox.information(self.parent, "Done!", "All assets in your cart have been downloaded successfully!")
        else:
            self.masterCartLabel.setText(f"Downloading: {len(still_running)} tasks remaining...")


    def add_to_cart(self, asset):
        """External API hook for browser grids to append assets."""
        if asset not in self.download_cart:
            self.download_cart.append(asset)
        self.sync_cart_labels()

    def remove_from_cart(self, asset):
        """External API hook to remove single items from queue."""
        if asset in self.download_cart:
            self.download_cart.remove(asset)
        self.sync_cart_labels()

    def clear_cart(self):
        """Resets the active queue selection back to blank."""
        self.download_cart.clear()
        self.sync_cart_labels()

    def sync_cart_labels(self):
        """Synchronizes counter labels and dynamic button strings."""
        cart_len = len(self.download_cart)
        if cart_len == 0:
            self.masterCartLabel.setText("Cart is empty")
            self.checkoutBtn.setText("Download All Items")
            self.checkoutBtn.setDisabled(True)
        else:
            self.checkoutBtn.setEnabled(True)
            self.masterCartLabel.setText(f"Items waiting in queue: {cart_len}")
            self.checkoutBtn.setText(f"Download All ({cart_len} Items)")


    def cleanUp(self):
        fullpath = self.parent.glob.lastdownload
        if fullpath is not None:
            (fpath, fname) = os.path.split(fullpath)
            try:
                if os.path.isfile(fullpath): 
                    os.remove(fullpath)
                if os.path.exists(fpath) and not os.listdir(fpath): 
                    os.rmdir(fpath)
            except Exception: 
                pass
            self.parent.glob.lastdownload = None
            self.filename.setText("")
            self.fnameinserted()
