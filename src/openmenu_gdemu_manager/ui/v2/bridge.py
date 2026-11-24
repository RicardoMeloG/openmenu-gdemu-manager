"""Connect approved cover workspace to original search/persistence services."""
import logging
from ...app.logger import logged_operation
from PIL import Image
from PySide6.QtCore import QObject,Signal,QTimer,Qt,Slot,QUrl
from PySide6.QtGui import QPixmap,QDesktopServices
from PySide6.QtWidgets import QWidget,QMessageBox,QMenu
from ...core.models import Candidate
from ...core.image_quality import normalize_cover,analyze_image
from ...covers.search import load_candidate_image
from ...config.settings import load_settings,web_search_templates
from ...config.paths import INBOX_ORIGINALS_DIR
from ..workers import SearchWorker,start_worker
from ..image_qt import pil_to_pixmap
from . import catalog
from .catalog import tr
from .game_info import game_info_dialog,image_info_dialog
from .covers import CoverWorkspace
from .state import CoverStore


log = logging.getLogger(__name__)


class CoverSearchWorker(QObject):
    finished=Signal(object)
    error=Signal(str)

    def __init__(self, game, query, write_allowed):
        super().__init__()
        self.game,self.query,self.write_allowed=game,query,write_allowed
        self.cancelled=False

    def cancel(self):self.cancelled=True

    @logged_operation("search_covers")
    def run(self):
        log.info("Cover search started: game=%s query=%s", getattr(self.game,"name",""), self.query)
        worker=SearchWorker(self.game,self.query,write_allowed=self.write_allowed)
        worker.finished.connect(self.prepare)
        worker.error.connect(self.error.emit)
        worker.run()

    @logged_operation("prepare_cover_images")
    def prepare(self, payload):
        prepared=[]
        for candidate in payload.get('candidates',[]):
            if self.cancelled:break
            try:
                image=load_candidate_image(candidate)
                report=analyze_image(image)
                candidate.width,candidate.height=image.size
                candidate.quality_label,candidate.quality_score=report.label,report.score
                prepared.append((candidate,image,''))
            except Exception as exc:
                log.exception("Cover preparation failed: game=%s query=%s provider=%s image=%s",
                              getattr(self.game,"name",""), self.query, candidate.source, candidate.local_path or candidate.url)
                prepared.append((candidate,None,str(exc)))
        self.finished.emit({'items':prepared,'query':self.query,'cancelled':self.cancelled})


class CoverHost(QWidget):
    """Small UI adapter, without a second application controller or simulation."""
    def __init__(self, window):
        super().__init__(window)
        self.window=window
        self.store=CoverStore(window)
        self.hide()

    def refresh_collection(self):
        self.window.apply_filters()

    def confirm(self,title,body,callback,parent=None,**kwargs):
        dialog=QMessageBox(parent or self.window)
        dialog.setWindowTitle(title)
        dialog.setText(body)
        accept=dialog.addButton(catalog.action_label('select'),QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(catalog.action_label('cancel'),QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is accept:callback()

    def show_info(self,game,parent=None,image_key=None):
        if image_key:dialog=image_info_dialog(self,game,image_key,parent)
        else:dialog=game_info_dialog(self,game,parent)
        dialog.exec()


class ProductionWorkspace(CoverWorkspace):
    def __init__(self,host,real,*,auto_search=True):
        host.resize(host.window.size())
        self.real=real
        self.search_thread=None
        self.search_worker=None
        self.search_jobs=[]
        self.retry_thread=None
        self.retry_worker=None
        super().__init__(host,host.store.view(real))
        self.setWindowIcon(host.window.windowIcon())
        if auto_search:QTimer.singleShot(0,self.search)

    def pixmap(self,key):
        if not key:return QPixmap()
        if key not in self.cache:
            try:
                image=self.store.image(key)
                self.cache[key]=pil_to_pixmap(image,image.size)
                self.store.images[key]['failed']=False
            except (OSError,ValueError,KeyError):
                self.store.images[key]['failed']=True
                self.cache[key]=QPixmap()
        return self.cache[key]

    def normalized_pixmap(self,key):
        image=normalize_cover(self.store.image(key))
        return pil_to_pixmap(image,image.size)

    def search(self):
        query=self.session.query.strip()
        if not query:self.message(tr('empty_query'));return
        if self.search_thread is not None and self.search_thread.isRunning():return
        self.search_request+=1
        token=self.search_request
        self.gallery.search.setEnabled(False)
        self.gallery.search.setText(tr('searching'))
        self.message(tr('search_progress'))
        self.set_searching(True)
        worker=CoverSearchWorker(self.real,query,self.owner.window.write_allowed)
        self.active_token=token
        start_worker(worker,'search_thread','search_worker',self,
            on_finished=self.receive_search,
            on_error=self.receive_error)
        self.search_jobs.append(self.search_thread)
        # Keep running jobs alive after closing the detail, without late UI work.
        self.owner.window.cover_jobs.append(self.search_thread)

    def web_menu(self):
        from urllib.parse import quote_plus
        menu=QMenu(self)
        for template in web_search_templates(load_settings()):
            expanded=template['url'].format(query=quote_plus(self.session.query+' Dreamcast cover art'),raw_query=quote_plus(self.session.query),product_id=quote_plus(self.game.product or self.session.query))
            if QUrl(expanded).scheme()=='https':menu.addAction(template['name'],lambda u=expanded:QDesktopServices.openUrl(QUrl(u)))
        if self.game.product and not self.game.product.startswith('SLOT'):
            url='https://www.google.com/search?tbm=isch&q='+quote_plus(self.game.product+' Dreamcast cover')
            menu.addAction(self.game.product,lambda:QDesktopServices.openUrl(QUrl(url)))
        menu.addSeparator()
        def open_library():
            INBOX_ORIGINALS_DIR.mkdir(parents=True,exist_ok=True)
            self.owner.window.open_path(INBOX_ORIGINALS_DIR)
        menu.addAction(tr('open_cover_library'),open_library)
        menu.popup(self.gallery.web.mapToGlobal(self.gallery.web.rect().bottomLeft()))
        self.web_popup=menu

    def retry_image(self,key):
        if self.retry_thread is not None:return
        candidate=self.store.candidate_objects.get(key)
        if candidate is None:return super().retry_image(key)
        self.retry_key=key
        worker=RetryImageWorker(candidate)
        start_worker(worker,'retry_thread','retry_worker',self,self.retry_finished,self.retry_failed)
        self.owner.window.cover_jobs.append(self.retry_thread)
        self.message(tr('search_progress'))

    @Slot(object)
    def retry_finished(self,payload):
        if self._closed:return
        candidate,image=payload
        self.store.add_candidate(self.game,candidate,image,key=self.retry_key)
        self.cache.pop(self.retry_key,None)
        super().retry_image(self.retry_key)

    @Slot(str)
    def retry_failed(self,message):
        if not self._closed:self.message(tr('read_failed',reason=message))

    @Slot(object)
    def receive_search(self,payload):self.search_finished(payload,self.active_token)

    @Slot(str)
    def receive_error(self,message):self.search_failed(message,self.active_token)

    def set_searching(self,value):
        self.searching=value
        if not self.gallery.cards or self.gallery.spinner is not None:self.gallery.populate()

    def search_finished(self,payload,token):
        if self._closed or token!=self.search_request:return
        self.searching=False
        self.gallery.search.setEnabled(True)
        self.gallery.search.setText(catalog.action_label('search'))
        if payload.get('cancelled'):
            self.set_searching(False);self.message(tr('search_cancelled'));return
        keys=[]
        for candidate,image,error in payload['items']:
            key=self.store.add_candidate(self.game,candidate,image)
            if error:self.store.images[key]['failed']=True
            keys.append(key)
        self.session.results=keys
        self.session.result_query=payload['query']
        self.session.page=1
        self.results()
        self.message(tr('gallery_hint' if keys else 'no_results_hint'))

    def search_failed(self,message,token):
        if self._closed or token!=self.search_request:return
        self.set_searching(False)
        self.gallery.search.setEnabled(True)
        self.gallery.search.setText(catalog.action_label('search'))
        self.message(tr('read_failed',reason=message))

    def invalidate_requests(self,*args):
        super().invalidate_requests(*args)
        if self.search_worker is not None:self.search_worker.cancel()

    def import_paths(self,paths):
        super().import_paths(paths)
        for key in self.session.local:
            if key not in self.store.candidate_objects:
                item=self.store.images[key]
                self.store.candidate_objects[key]=Candidate('local',item['title'],100,local_path=item['local_path'])
                from ...core.dedupe import exact_image_hash
                item['contentId']=exact_image_hash(self.store.image(key))


class RetryImageWorker(QObject):
    finished=Signal(object);error=Signal(str)
    def __init__(self,candidate):super().__init__();self.candidate=candidate
    @logged_operation("retry_cover_image")
    def run(self):
        try:self.finished.emit((self.candidate,load_candidate_image(self.candidate)))
        except Exception as exc:
            log.exception("Cover retry failed: provider=%s image=%s", self.candidate.source, self.candidate.local_path or self.candidate.url)
            self.error.emit(str(exc))
