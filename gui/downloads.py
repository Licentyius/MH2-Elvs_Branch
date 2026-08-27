"""
    License information: data/licenses/makehuman_license.txt
    Author: black-punkduck, Elvaerwyn_MH2 2026 V1.3

    Classes:
    * DownLoadImport
"""
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLineEdit, QLabel,
    QMessageBox, QRadioButton, QCheckBox, QComboBox, QStyle, QVBoxLayout
    )

from PySide6.QtCore import Qt
from gui.tablewindow import MHSelectAssetWindow
from gui.common import ErrorBox, WorkerThread, MHBusyWindow, IconButton, MHFileRequest, MHProgWindow
from opengl.texture import MH_Thumb
from core.importfiles import AssetPack

import os

class DownLoadImport(QVBoxLayout):
    def __init__(self, parent, view, displaytitle):
        self.parent = parent
        self.glob = parent.glob
        self.env = parent.env
        self.view = view
        self.displaytitle = displaytitle
        self.bckproc = None     # will contain process running in parallel
        self.error   = None     # will contain possible error text
        self.zipfile = None     # last loaded zipfile
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

        stdmesh =  self.env.release_info["standardmesh"]
        self.parentmesh = self.glob.baseClass.baseInfo.get("parentmesh")

        assetname = os.path.split(self.env.release_info["url_assetlist"])[1]
        assetpackname = os.path.split(self.env.release_info["url_assetpacklist"])[1]

        dl = os.path.join(self.env.path_userdata, "downloads", self.env.basename)   # normal assets will contain own asset lists
        self.assetlistpath = os.path.join(dl, assetname)

        pdl = os.path.join(self.env.path_userdata, "downloads", stdmesh)            # pack list will be in standard path
        self.env.mkdir(pdl)                                                         # create folder if not there

        self.assetpacklistpath = os.path.join(pdl, assetpackname)

        self.getAssetPackList()

        # Pre-load and translate your asset dictionary right here during boot setup 
        # so the button can see your amount of items and calculate the time estimate instantly!
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

        self.download_cart = []
        self.cart_processing = False

        self.latest = self.assets.testAssetList(self.assetlistpath)
        if self.latest is None:
            self.asdlbutton = QPushButton("Download Asset and Assetpack list")
        else:
            self.asdlbutton = QPushButton("Replace Current Asset Lists [" + self.latest + "]")
            
        self.asdlbutton.setEnabled(True)
        self.asdlbutton.clicked.connect(self.listDownLoad)
        self.asdlbutton.setToolTip("Asset list are needed to load single assets...")
        self.addWidget(self.asdlbutton)

        # --- PRE-CALCULATED SYNC THUMBNAIL CACHE INTERFACE ELEMENT ---
        self.syncThumbsButton = QPushButton("Sync Thumbnail Cache (Download All)")
        self.syncThumbsButton.setEnabled(self.latest is not None)
        
        # Calculate exactly how many thumbnails exist in this repository version
        total_thumbs_to_cache = 0
        if hasattr(self, 'json') and self.json:
            for key, rec in self.json.items():
                if isinstance(rec, dict):
                    f_dict = rec.get("files")
                    if isinstance(f_dict, dict) and f_dict.get("thumb"):
                        total_thumbs_to_cache += 1

        if total_thumbs_to_cache > 0:
            # Calibrated strictly against your real-world benchmark of ~30 mins for 2664 files
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

        vlayout.addWidget(QLabel("\nBrowse in list to find your asset."))
        self.browsebutton=QPushButton("Asset Browser")
        self.browsebutton.setEnabled(self.latest is not None)
        self.browsebutton.clicked.connect(self.selectfromList)
        self.browsebutton.setToolTip("Browse downloaded asset list.")
        vlayout.addWidget(self.browsebutton)

        gb.setLayout(vlayout)
        self.addWidget(gb)

        gb = QGroupBox("Asset Pack")
        gb.setObjectName("subwindow")

        # name and link
        #
        ilayout = QVBoxLayout()
        ilayout.addWidget(QLabel("Select asset pack:"))

        self.combo = QComboBox()
        self.combo.addItems(self.packitems)
        self.combo.setToolTip("An asset pack is a zip file,\nDownload of the standard assets can be done here.\nThey also can be downloaded manually\nand extracted with extract button below")
        self.combo.currentIndexChanged.connect(self.packNameChanged)

        ilayout.addWidget(self.combo)

        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel("or select and copy an URL from:"))
        linklabel = QLabel()
        ltext = "<a href='" + self.env.release_info["url_assetpacks"] + "'>Asset Packs</a>"
        linklabel.setToolTip("Opens browser to search for asset packs.\nAn asset pack usually ends with .zip")
        linklabel.setText(ltext)
        linklabel.setOpenExternalLinks(True)
        hlayout.addWidget(linklabel)
        ilayout.addLayout(hlayout)

        self.packname = QLineEdit("")
        self.packname.editingFinished.connect(self.packinserted)
        ilayout.addWidget(self.packname)

        self.dlbutton=QPushButton("Download Asset Pack")
        self.dlbutton.clicked.connect(self.downLoad)
        ilayout.addWidget(self.dlbutton)

        userpath = QLabel("Destination user path for base: "  + self.env.basename + "\n"+ self.env.path_userdata)
        userpath.setToolTip("Files will be extracted to " + self.env.basename + " folders in "  + self.env.path_userdata)
        ilayout.addWidget(userpath)

        if self.env.admin:
            syspath = QLabel("Destination system path for base: " + self.env.basename + "\n"+ self.env.path_sysdata)
            syspath.setToolTip("Files will be extracted to " + self.env.basename + " folders in "  + self.env.path_sysdata)
            ilayout.addWidget(syspath)

            self.userbutton = QRadioButton("Install in your user path")
            self.userbutton.setChecked(True)
            self.systembutton = QRadioButton("Install in system path")
            self.userbutton.toggled.connect(self.setMethod)
            self.systembutton.toggled.connect(self.setMethod)
            ilayout.addWidget(self.userbutton)
            ilayout.addWidget(self.systembutton)


        ilayout.addWidget(QLabel("\nAfter download use the filename inserted by\nprogram or select an already downloaded\nasset pack and press extract:"))

        #  enter zip file name
        hlayout = QHBoxLayout()
        self.zipfilebuttton = IconButton(0, os.path.join(self.env.path_sysicon, "files.png"), "Select zip file.", self.searchzipfile, 16)
        hlayout.addWidget(self.zipfilebuttton)

        self.filename = QLineEdit("")
        self.filename.editingFinished.connect(self.fnameinserted)
        self.filename.setText(self.parent.glob.lastdownload)
        hlayout.addWidget(self.filename)
        ilayout.addLayout(hlayout)

        self.savebutton=QPushButton("Extract")
        self.savebutton.clicked.connect(self.extractZip)
        ilayout.addWidget(self.savebutton)

        ilayout.addWidget(QLabel("\nIf the downloaded file is no longer needed,\npress cleanup to delete the temporary folder"))
        self.clbutton=QPushButton("Clean Up")
        self.clbutton.clicked.connect(self.cleanUp)
        ilayout.addWidget(self.clbutton)
        gb.setLayout(ilayout)
        self.addWidget(gb)
        self.packinserted()
        self.fnameinserted()
        # ----------------------------------------------------
        # BATCH CART PANEL Begins
        # ----------------------------------------------------
        checkout_panel = QGroupBox("Batch Asset Cart")
        panel_layout = QHBoxLayout(checkout_panel)

        self.masterCartLabel = QLabel("Cart is empty")
        panel_layout.addWidget(self.masterCartLabel)
        panel_layout.addStretch()

        self.checkoutBtn = QPushButton("Download Cart Items")
        self.checkoutBtn.setDisabled(True) 
        
        from PySide6.QtGui import QIcon
        icon_path = os.path.join(self.env.path_sysicon, "cart.png")
        
        if os.path.exists(icon_path):
            self.checkoutBtn.setIcon(QIcon(icon_path))
        else:
            dl_icon = self.parent.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
            self.checkoutBtn.setIcon(dl_icon)
            
        self.checkoutBtn.clicked.connect(self.on_checkout_clicked)
        panel_layout.addWidget(self.checkoutBtn)
        self.addWidget(checkout_panel)

        # --- THE FULL REPOSITORY SYSTEM SYNCHRONIZER BUTTON ---
        self.syncRepoButton = QPushButton("Sync Full Repository (Download All)")
        self.syncRepoButton.setEnabled(self.latest is not None)
        
        total_assets_to_download = 0
        if hasattr(self, 'json') and self.json:
            total_assets_to_download = len(self.json)

        if total_assets_to_download > 0:
            self.syncRepoButton.setText(f"Sync Full Repository ({total_assets_to_download} Items)")
        else:
            self.syncRepoButton.setText("Sync Full Repository (Download All)")

        self.syncRepoButton.clicked.connect(self.syncFullRepositoryCall)
        self.syncRepoButton.setToolTip("Automatically download every single asset in the catalog at once.")
        self.addWidget(self.syncRepoButton)

    def searchzipfile(self):
        freq = MHFileRequest(self.glob, "Select zipfile", "compressed file (*.zip)", "")
        name = freq.request()
        if name is not None:
            self.filename.setText(name)
            self.fnameinserted()

    def defaultList(self):
        """
        create an assetpack list according to base, parentmesh and given names
        """
        self.packitems= [""]
        self.packurls= [""]
        sysassets  = self.env.release_info["url_systemassets"]
        for elem in sysassets:
            base = elem.get("base")
            if base == self.env.basename or base == "*" or self.parentmesh == base:
                self.packitems.append(elem["title"])
                self.packurls.append(elem["url"])

    def formList(self, packs):
        self.packitems= []
        self.packurls= []
        for key, elem in packs.items():
            base = elem.get("base")
            if base == self.env.basename or base == "*" or self.parentmesh == base:
                if "url" in elem:
                    if "descr" in elem:
                        text = elem["descr"]
                    else:
                        text = key
                    if "license" in elem:
                        text += ", " + elem["license"]
                    if "size" in elem:
                        text += " (" + str(elem["size"]) + " mb)"
                    self.packitems.append(text)
                    self.packurls.append(elem["url"])

    def getAssetPackList(self):
        self.assetpackjson = self.env.readJSON(self.assetpacklistpath)
        if self.assetpackjson is not None and "packs" in self.assetpackjson:
            self.formList(self.assetpackjson["packs"])   
        else:
            self.defaultList()

    def packNameChanged(self, index):
        f = self.env.release_info["url_fileserver"] + "/" + self.packurls[index]
        self.packname.setText(f)
        self.packinserted()

    def setMethod(self, value):
        if self.userbutton.isChecked():
            self.use_userpath = True
        else:
            self.use_userpath = False

    def packinserted(self):
        self.dlbutton.setEnabled(len(self.packname.text()) > 0)

    def fnameinserted(self):
        self.savebutton.setEnabled(len(self.filename.text()) > 0)

    def selectfromList(self):
        if self.assetjson is None:
            self.assetjson =  self.assets.alistReadJSON(self.env, self.assetlistpath)
        w = self.glob.showSubwindow("loadasset", self, MHSelectAssetWindow, self.assetjson)

    def par_unzip(self, bckproc, *args):
        filename = self.filename.text()
        tempdir, error = self.assets.unZip(filename)
        if error is not None:
            self.error = error
            return
        destpath = self.env.path_sysdata if self.use_userpath is False else self.env.path_userdata
        fname = os.path.basename(filename)
        if fname.startswith("newbase_"):
            base = fname[8:-4]
            parentmesh = None
        else:
            base = self.env.basename
            parentmesh = self.parentmesh

        self.env.logLine(1, "Unzip into: " + tempdir + " >" + destpath + " Mesh: " + base)
        self.assets.copyAssets(tempdir, destpath, base, parentmesh=parentmesh, debugfunc=self.env.logLine)

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
        tempdir = args[0][0]
        filename = args[0][1]
        self.error = None
        self.env.logLine(1, "Download " + self.packname.text() + " to " + tempdir)
        (err, text) = self.assets.getAssetPack(self.packname.text(), tempdir, filename, unzip=False, responsefunc=self.displayProgress)
        self.error = text

    def finishLoad(self):
        if self.prog_window is not None:
            self.prog_window.progress.close()
            self.prog_window = None
        if self.error:
            ErrorBox(self.parent, self.error)
        else:
            QMessageBox.information(self.parent, "Done!", self.bckproc.finishmsg)
        self.bckproc = None 

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

        if hasattr(self, 'syncThumbsButton') and self.syncThumbsButton:
            self.syncThumbsButton.setEnabled(self.latest is not None)
            total_thumbs = 0
            if hasattr(self, 'json') and self.json:
                total_thumbs = sum(1 for k, r in self.json.items() if isinstance(r, dict) and "files" in r and "thumb" in r["files"])
            
            if total_thumbs > 0:
                real_world_mins = int((total_thumbs * 0.675) / 60)
                if real_world_mins < 1: 
                    real_world_mins = 1
                slow_m = int(real_world_mins * 2.5)
                
                self.syncThumbsButton.setText(f"Sync Thumbnail Cache ({total_thumbs} Items)")
                self.syncThumbsButton.setToolTip(
                    f"Download all available thumbnails.<br>"
                    f"<b>Estimated Duration:</b> ~{real_world_mins} mins.<br>"
                    f"<i>Note: May take up to {slow_m} mins on slower networks.</i>"
                )

        self.getAssetPackList()
        
        if hasattr(self, 'combo') and self.combo is not None:
            self.combo.clear()
            self.combo.addItems(self.packitems)

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

    def par_listdownload(self, bckproc, *args):
        destination = args[0][0]
        destination2 = args[0][1]
        self.error = None
        i = 0
        for fname in  self.env.release_info["url_assetlist"],  self.env.release_info["url_assetpacklist"]:
            dest = args[0][i]
            i += 1
            self.prog_window.setValueAndText(0, "Download " + fname + " to " + dest)
            loaded, text = self.assets.getUrlFile(fname, dest, responsefunc=self.displayProgress)
            self.error = text
            if loaded is False:
                return

    def listDownLoad(self):
        if self.bckproc == None:
            self.assetjson = None

            self.prog_window = MHProgWindow("Download Lists", 1000)
            self.prog_window.progress.forceShow()
            self.bckproc = WorkerThread(self.par_listdownload, self.assetlistpath, self.assetpacklistpath)
            self.bckproc.start()
            self.bckproc.finishmsg = "Download finished"
            self.bckproc.finished.connect(self.finishListLoad)

    def par_thumb_cache_download(self, bckproc, *args):
        if self.assetjson is None:
            self.assetjson = self.assets.alistReadJSON(self.env, self.assetlistpath)
        if not self.assetjson:
            self.error = "Asset list cache is empty. Please download lists first."
            return
        self.error = None
        all_tasks = []
        for key, rec in self.json.items():
            if isinstance(rec, dict):
                files_dict = rec.get("files")
                if isinstance(files_dict, dict):
                    thumb_url = files_dict.get("thumb")
                    if thumb_url:
                        all_tasks.append((key, thumb_url))
        if not all_tasks:
            return
        needed_tasks = []
        for asset_key, thumb_url in all_tasks:
            display_title = self.json[asset_key].get("title", asset_key)
            if display_title.lower().endswith(".png"):
                thumb_filename = display_title[:-4] + ".thumb"
            else:
                thumb_filename = display_title + ".thumb"
            dest_file = os.path.join(self.env.path_userdata, "downloads", self.env.basename, "render", thumb_filename)
            if not os.path.exists(dest_file):
                needed_tasks.append((asset_key, thumb_url, dest_file))
        if not needed_tasks:
            if hasattr(bckproc, 'associated_window') and bckproc.associated_window:
                bckproc.associated_window.setValueAndText(1000, "Cache is already 100% up to date!")
            elif self.prog_window:
                self.prog_window.setValueAndText(1000, "Cache is already 100% up to date!")
            self.bckproc.finishmsg = "Your thumbnail cache is already complete! No downloads were needed."
            return
        total_count = len(needed_tasks)
        self.env.logLine(1, f"Syncing cache: downloading {total_count} missing thumbnails.")
        for idx, (asset_key, thumb_url, dest_file) in enumerate(needed_tasks):
            display_title = self.json[asset_key].get("title", asset_key)
            progress_percent = int((idx / total_count) * 1000)
            msg_text = f"Caching Thumbs ({idx}/{total_count}): {display_title}"
            if hasattr(bckproc, 'associated_window') and bckproc.associated_window:
                bckproc.associated_window.setValueAndText(progress_percent, msg_text)
            elif self.prog_window:
                self.prog_window.setValueAndText(progress_percent, msg_text)
            try:
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                loaded, text = self.assets.getUrlFile(thumb_url, dest_file)
                if loaded and os.path.exists(dest_file):
                    from opengl.texture import MH_Thumb
                    thumb_engine = MH_Thumb()
                    thumb_engine.rescale(dest_file)
            except Exception as e:
                self.env.logLine(1, f"Failed caching thumbnail for {display_title}: {str(e)}")

    def syncAllThumbnailsCall(self):
        if self.bckproc is None:
            if self.assetjson is None:
                self.assetjson = self.assets.alistReadJSON(self.env, self.assetlistpath)
                if isinstance(self.assetjson, list):
                    self.json = {item.get("title", item.get("id", str(i))): item for i, item in enumerate(self.assetjson) if isinstance(item, dict)}
                else:
                    self.json = self.assetjson if self.assetjson else {}
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
            self.env.logLine(8, "Get: " + elem + " >" + destination)
            if hasattr(bckproc, 'associated_window') and bckproc.associated_window is not None:
                bckproc.associated_window.setLabelText("Loading: " + elem)
            elif self.prog_window is not None:
                self.prog_window.setLabelText("Loading: " + elem)
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
                else:
                    self.error = "target not found, please restart makehuman"
        self.error = text

    def parentAsset(self, key):
        """
        Calculates the path of a parent asset.
        """
        pobj = self.assetjson[key]["belongs_to"]
        if pobj["belonging_is_assigned"] is False:
            return False, self.env.path_userdata
        else:
            if "belongs_to_core_asset" in pobj:
                (mtype, folder) = pobj["belongs_to_core_asset"].split("/", 2)
                if mtype == "eyes":
                    path = self.env.existDataDir(mtype, self.env.basename)
                else:
                    path = self.env.existDataDir(mtype, self.env.basename, folder)

                if path is None:
                    self.env.logLine(1, f" [Sync Warning] Core asset link broken in legacy data: {pobj['belongs_to_core_asset']}. Falling back to default directory.")
                    return False, self.env.path_userdata

                return True, path

            parentkey = str(pobj["belongs_to_id"])
            mtype = self.assetjson[parentkey]["type"]
            if mtype == "model":
                mtype = "skins"
            folder = self.assets.titleToFileName(pobj["belongs_to_title"])

            path = self.env.existDataDir(mtype, self.env.basename, folder)
            if path is None:
                return False, self.env.existDataDir(mtype, self.env.basename)
            return True, path

    def singleDownLoad(self, assetname):
        """
        Executes single asset downloads.
        """
        if self.assetjson is None:
            self.assetjson = self.assets.alistReadJSON(self.env, self.assetlistpath)

        if self.assetjson is None:
            self.env.logLine(1, f" [Sync Error] Asset JSON catalog could not be read for: {assetname}")
            return None

        if assetname in self.assetjson:
            item = self.assetjson[assetname]
            folder = item.get("folder")
        else:
            self.env.logLine(1, f" [Sync Warning] Asset '{assetname}' missing from JSON catalog lists. Skipping.")
            return None

        mtype, flist = self.assets.alistGetFiles(self.assetjson, assetname)

        # Removed the rigid 'supportedclasses' array restrictions entirely. 
        # Any class added over the last 20 years or custom types will parse cleanly using their raw string types.
        self.env.logLine(8, "Assets of type " + mtype + " >" + folder)
        for elem in flist:
            self.env.logLine(8, " " + elem)

        if mtype == "material":
            okay, path = self.parentAsset(assetname)
            if okay is False:
                # If a material's parent asset path is missing or undefined, it automatically drops into the standard user materials path.
                if path is None:
                    path = os.path.join(self.env.path_userdata, self.env.basename, "materials")
                
                self.env.logLine(8, " [Sync Auto-Route] Defaulting material asset path to: " + path)

            folder, err = self.assets.createMaterialsFolder(path)
        else:
            folder, err = self.assets.alistCreateFolderFromTitle(self.env.path_userdata, self.env.basename, mtype, folder)

        if folder is None:
            self.env.logLine(1, f" [Sync Warning] Skipping path allocation block for '{assetname}': {err}")
            return None

        local_prog_window = MHBusyWindow("Download files to " + folder, "loading ...")
        local_prog_window.progress.forceShow()
        
        worker = WorkerThread(self.par_filesdownload, folder, flist)
        worker.finishmsg = "Download finished"
        worker.associated_window = local_prog_window
        
        if not hasattr(self, 'active_parallel_workers'):
            self.active_parallel_workers = []
        self.active_parallel_workers.append((assetname, worker))
        
        if hasattr(self, 'cart_processing') and self.cart_processing:
            worker.finished.connect(self.advance_full_repo_sync_loop)
        else:
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
        button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        button.setEnabled(False)
        self.update_cart_time_estimate()

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
        self.masterCartLabel.setText("Processing batch queue...")
        self.cart_processing = True
        
        next_asset = self.download_cart[0]
        self.current_asset = next_asset
        active_worker = self.singleDownLoad(next_asset)
        
        if active_worker is None:
            if next_asset in self.download_cart:
                self.download_cart.remove(next_asset)
            self.advance_sequential_cart_queue()

    def advance_sequential_cart_queue(self):
        sender_worker = self.sender()
        if sender_worker and hasattr(sender_worker, 'associated_window') and sender_worker.associated_window is not None:
            sender_worker.associated_window.progress.close()
            sender_worker.associated_window = None

        if self.bckproc is not None:
            self.assets.cleanupUnzip()
            self.bckproc = None
            
        if self.download_cart:
            self.download_cart.pop(0)
            
        if self.download_cart:
            cart_len = len(self.download_cart)
            self.masterCartLabel.setText(f"Batch processing: {cart_len} tasks remaining...")
            next_asset = self.download_cart[0]
            self.current_asset = next_asset
            active_worker = self.singleDownLoad(next_asset)
            if active_worker is None:
                self.advance_sequential_cart_queue()
        else:
            self.cart_processing = False
            self.masterCartLabel.setText("All items downloaded successfully! Cart empty.")
            self.checkoutBtn.setEnabled(False)
            self.current_asset = None
            self.glob.MainWindow.syncRepositories()
            QMessageBox.information(self.parent, "Success!", "All assets in your cart have been downloaded successfully!")

    def finish_parallel_load(self):
        sender_worker = self.sender()
        if sender_worker and hasattr(sender_worker, 'associated_window') and sender_worker.associated_window is not None:
            sender_worker.associated_window.progress.close()
            sender_worker.associated_window = None
        elif self.prog_window is not None:
            self.prog_window.progress.close()
            self.prog_window = None

        still_running = []
        for asset, worker in self.active_parallel_workers:
            if worker is not None and hasattr(worker, 'isRunning') and worker.isRunning():
                still_running.append((asset, worker))
            else:
                if asset in self.download_cart:
                    self.download_cart.remove(asset)

        self.active_parallel_workers = still_running

        if not still_running:
            self.cart_processing = False
            self.download_cart.clear()
            self.masterCartLabel.setText("All items downloaded successfully! Cart empty.")
            self.checkoutBtn.setEnabled(False)
            QMessageBox.information(self.parent, "Done!", "All assets in your cart have been downloaded successfully!")
        else:
            self.masterCartLabel.setText(f"Downloading: {len(still_running)} tasks remaining...")

    def cleanUp(self):
        fullpath = self.parent.glob.lastdownload
        if fullpath is not None:
            (fpath, fname) = os.path.split(fullpath)
            try:
                if os.path.isfile(fullpath):
                    os.remove(fullpath)
                if os.path.exists(fpath) and not os.listdir(fpath):
                    os.rmdir(fpath)
            except Exception as e:
                self.env.logLine(1, f"Clean Up asset warning: {str(e)}")
            self.parent.glob.lastdownload = None
            self.filename.setText("")
            self.fnameinserted()
    def syncFullRepositoryCall(self):
        """Initializes a full database sweep loop pass, downloading every asset in the JSON list sequentially."""
        if self.bckproc is not None:
            ErrorBox(self.parent, "Another background installation process is currently active. Please wait.")
            return

        if self.assetjson is None:
            self.assetjson = self.assets.alistReadJSON(self.env, self.assetlistpath)

        if not self.assetjson:
            ErrorBox(self.parent, "Asset database list layout is missing or empty. Please refresh lists first.")
            return

        # Extract all asset identification keys straight out of your loaded catalog mapping array
        self.repo_sync_queue = list(self.assetjson.keys())
        self.total_repo_sync_count = len(self.repo_sync_queue)
        
        if self.total_repo_sync_count == 0:
            return

        self.cart_processing = True
        self.syncRepoButton.setEnabled(False)
        
        # Open up your standalone global application tracking progress window box widget
        self.prog_window = MHProgWindow("Synchronizing Complete Asset Repository", 1000)
        self.prog_window.progress.forceShow()
        
        # Fire up the loop tracking runner pass for item index row 0
        self.advance_full_repo_sync_loop()

    def advance_full_repo_sync_loop(self):
        """Processes the next element waiting in your master repository synchronization queue array."""
        sender_worker = self.sender()
        if sender_worker and hasattr(sender_worker, 'associated_window') and sender_worker.associated_window is not None:
            sender_worker.associated_window.progress.close()
            sender_worker.associated_window = None

        if self.bckproc is not None:
            self.assets.cleanupUnzip()
            self.bckproc = None

        if not hasattr(self, 'repo_sync_queue') or not self.repo_sync_queue:
            # SCRIPT SYNC RUN FULLY COMPLETE! Clean up all remaining system variables and refresh UI layouts
            self.cart_processing = False
            if self.prog_window is not None:
                self.prog_window.progress.close()
                self.prog_window = None
                
            self.syncRepoButton.setEnabled(True)
            self.syncRepoButton.setText(f"Sync Full Repository ({len(self.json)} Items)")
            self.glob.MainWindow.syncRepositories()
            
            QMessageBox.information(self.parent, "Mirror Sync Complete!", "The entire asset repository has been completely downloaded and mirrored successfully onto your local system drive folders!")
            return

        # Isolate the next raw text target string key inside the array queue index
        next_target_asset = self.repo_sync_queue.pop(0)
        current_idx = self.total_repo_sync_count - len(self.repo_sync_queue)
        progress_ratio = int((current_idx / self.total_repo_sync_count) * 1000)
        
        # Paint the active download status updates straight across your UI progress banner elements
        status_msg = f"Syncing Complete Repo ({current_idx}/{self.total_repo_sync_count}): {next_target_asset}"
        if self.prog_window:
            self.prog_window.setValueAndText(progress_ratio, status_msg)

        # Execute your existing file download framework worker logic tracking methods
        worker = self.singleDownLoad(next_target_asset)
        
        if worker is None:
            # If an entry maps a bad file block or returns an immediate initialization error, jump to next loop sequence
            self.advance_full_repo_sync_loop()
