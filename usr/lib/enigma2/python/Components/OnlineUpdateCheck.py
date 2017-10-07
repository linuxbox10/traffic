# Embedded file name: /usr/lib/enigma2/python/Components/OnlineUpdateCheck.py
from boxbranding import getImageVersion, getImageBuild, getImageDistro, getMachineBrand, getMachineName, getMachineBuild, getImageType, getBoxType, getFeedsUrl
from time import time
from enigma import eTimer
import Components.Task
from Components.Ipkg import IpkgComponent
from Components.config import config
from Components.About import about
import urllib2, socket, sys
error = 0

def OnlineUpdateCheck(session = None, **kwargs):
    global onlineupdatecheckpoller
    onlineupdatecheckpoller.start()


class FeedsStatusCheck:

    def __init__(self):
        self.ipkg = IpkgComponent()
        self.ipkg.addCallback(self.ipkgCallback)

    def IsInt(self, val):
        try:
            int(val)
            return True
        except ValueError:
            return False

    def getFeedStatus(self):
        status = '1'
        trafficLight = 'unknown'
        if about.getIfConfig('eth0').has_key('addr') or about.getIfConfig('eth1').has_key('addr') or about.getIfConfig('wlan0').has_key('addr') or about.getIfConfig('wlan3').has_key('addr') or about.getIfConfig('ra0').has_key('addr'):
            try:
                print '[OnlineVersionCheck] Checking feeds state'
                req = urllib2.Request('http://vuplus-images-vix.does-it.net/openvix/TrafficLightState.php')
                d = urllib2.urlopen(req)
                trafficLight = d.read()
            except urllib2.HTTPError as err:
                print '[OnlineVersionCheck] ERROR:', err
                trafficLight = err.code
            except urllib2.URLError as err:
                print '[OnlineVersionCheck] ERROR:', err.reason[0]
                trafficLight = err.reason[0]
            except urllib2 as err:
                print '[OnlineVersionCheck] ERROR:', err
                trafficLight = err
            except:
                print '[OnlineVersionCheck] ERROR:', sys.exc_info()[0]
                trafficLight = -2

            if not self.IsInt(trafficLight) and getImageType() != 'release':
                trafficLight = 'unknown'
            elif trafficLight == 'stable':
                status = '0'
            config.softwareupdate.updateisunstable.setValue(status)
            print '[OnlineVersionCheck] PASSED:', trafficLight
            return trafficLight
        else:
            print '[OnlineVersionCheck] ERROR: -2'
            return -2

    feed_status_msgs = {'stable': _('Feeds status: Stable'),
     'unstable': _('Feeds status: Unstable'),
     'updating': _('Feeds status: Updating'),
     '-2': _('ERROR: No network found'),
     '403': _('ERROR: Forbidden'),
     '404': _('ERROR: No internet found'),
     'inprogress': _('ERROR: Check is already running in background, please wait a few minutes and try again'),
     'unknown': _('Feeds status: Unknown')}

    def getFeedsBool(self):
        global error
        feedstatus = feedsstatuscheck.getFeedStatus()
        if feedstatus in (-2, 403, 404):
            print '[OnlineVersionCheck] Error %s' % feedstatus
            return str(feedstatus)
        if error:
            print '[OnlineVersionCheck] Check already in progress'
            return 'inprogress'
        if feedstatus == 'updating':
            print '[OnlineVersionCheck] Feeds Updating'
            return 'updating'
        if feedstatus in ('stable', 'unstable', 'unknown'):
            print '[OnlineVersionCheck]', feedstatus.title()
            return str(feedstatus)

    def getFeedsErrorMessage(self):
        feedstatus = feedsstatuscheck.getFeedsBool()
        if feedstatus == -2:
            return _('Your %s %s has no network access, please check your network settings and make sure you have network cable connected and try again.') % (getMachineBrand(), getMachineName())
        if feedstatus == 404:
            return _('Your %s %s is not connected to the internet, please check your network settings and try again.') % (getMachineBrand(), getMachineName())
        if feedstatus in ('updating', 403):
            return _('Sorry feeds are down for maintenance, please try again later. If this issue persists please check vuplus-images.co.uk.')
        if error:
            return _('There has been an error, please try again later. If this issue persists, please check vuplus-images.co.uk')

    def startCheck(self):
        global error
        error = 0
        self.updating = True
        self.ipkg.startCmd(IpkgComponent.CMD_UPDATE)

    def ipkgCallback(self, event, param):
        global error
        config.softwareupdate.updatefound.setValue(False)
        if event == IpkgComponent.EVENT_ERROR:
            error += 1
        elif event == IpkgComponent.EVENT_DONE:
            if self.updating:
                self.updating = False
                self.ipkg.startCmd(IpkgComponent.CMD_UPGRADE_LIST)
            elif self.ipkg.currentCommand == IpkgComponent.CMD_UPGRADE_LIST:
                self.total_packages = len(self.ipkg.getFetchedList())
                if self.total_packages and (getImageType() != 'release' or config.softwareupdate.updateisunstable.value == '1' and config.softwareupdate.updatebeta.value or config.softwareupdate.updateisunstable.value == '0'):
                    print '[OnlineVersionCheck] %s Updates available' % self.total_packages
                    config.softwareupdate.updatefound.setValue(True)


feedsstatuscheck = FeedsStatusCheck()

class OnlineUpdateCheckPoller:

    def __init__(self):
        self.timer = eTimer()

    MIN_INITIAL_DELAY = 2400
    checktimer_Notifier_Added = False

    def start(self, *args, **kwargs):
        if self.onlineupdate_check not in self.timer.callback:
            self.timer.callback.append(self.onlineupdate_check)
        if not self.checktimer_Notifier_Added:
            config.softwareupdate.checktimer.addNotifier(self.start, initial_call=False, immediate_feedback=False)
            self.checktimer_Notifier_Added = True
            minimum_delay = self.MIN_INITIAL_DELAY
        else:
            minimum_delay = 60
        last_run = config.softwareupdate.updatelastcheck.getValue()
        gap = config.softwareupdate.checktimer.value * 3600
        delay = last_run + gap - int(time())
        if delay < minimum_delay:
            delay = minimum_delay
        if delay > gap:
            delay = gap
        self.timer.startLongTimer(delay)
        when = time() + delay

    def stop(self):
        if self.version_check in self.timer.callback:
            self.timer.callback.remove(self.onlineupdate_check)
        self.timer.stop()

    def onlineupdate_check(self):
        if config.softwareupdate.check.value:
            Components.Task.job_manager.AddJob(self.createCheckJob())
        self.timer.startLongTimer(config.softwareupdate.checktimer.value * 3600)
        config.softwareupdate.updatelastcheck.setValue(int(time()))
        config.softwareupdate.updatelastcheck.save()

    def createCheckJob(self):
        job = Components.Task.Job(_('OnlineVersionCheck'))
        task = Components.Task.PythonTask(job, _('Checking for Updates...'))
        task.work = self.JobStart
        task.weighting = 1
        return job

    def JobStart(self):
        config.softwareupdate.updatefound.setValue(False)
        if getImageType() != 'release' and feedsstatuscheck.getFeedsBool() == 'unknown' or getImageType() == 'release' and feedsstatuscheck.getFeedsBool() in ('stable', 'unstable'):
            print '[OnlineVersionCheck] Starting background check.'
            feedsstatuscheck.startCheck()
        else:
            print '[OnlineVersionCheck] No feeds found, skipping check.'


onlineupdatecheckpoller = OnlineUpdateCheckPoller()

class VersionCheck:

    def __init__(self):
        pass

    def getStableUpdateAvailable(self):
        if config.softwareupdate.updatefound.value and config.softwareupdate.check.value:
            if getImageType() != 'release' or config.softwareupdate.updateisunstable.value == '0':
                print '[OnlineVersionCheck] New Release updates found'
                return True
            else:
                print '[OnlineVersionCheck] skipping as unstable is not wanted'
                return False
        else:
            return False

    def getUnstableUpdateAvailable(self):
        if config.softwareupdate.updatefound.value and config.softwareupdate.check.value:
            if getImageType() != 'release' or config.softwareupdate.updateisunstable.value == '1' and config.softwareupdate.updatebeta.value:
                print '[OnlineVersionCheck] New Experimental updates found'
                return True
            else:
                print '[OnlineVersionCheck] skipping as beta is not wanted'
                return False
        else:
            return False


versioncheck = VersionCheck()

def kernelMismatch():
    import zlib
    import re
    kernelversion = about.getKernelVersionString().strip()
    if kernelversion == 'unknown':
        print '[OnlineVersionCheck][kernelMismatch] unable to retrieve kernel version from STB'
        return False
    uri = '%s/%s/Packages.gz' % (getFeedsUrl(), getMachineBuild())
    try:
        req = urllib2.Request(uri)
        d = urllib2.urlopen(req)
        gz_data = d.read()
    except:
        print '[OnlineVersionCheck][kernelMismatch] error fetching %s' % uri
        return False

    try:
        packages = zlib.decompress(gz_data, 16 + zlib.MAX_WBITS)
    except:
        print '[OnlineVersionCheck][kernelMismatch] failed to decompress gz_data'
        return False

    pattern = 'kernel-([0-9]+[.][0-9]+[.][0-9]+)'
    matches = re.findall(pattern, packages)
    if matches:
        match = sorted(matches, key=lambda s: list(map(int, s.split('.'))))[-1]
        if match != kernelversion:
            print '[OnlineVersionCheck][kernelMismatch] kernel mismatch found. STB kernel=%s, feeds kernel=%s' % (kernelversion, match)
            return True
    print '[OnlineVersionCheck][kernelMismatch] no kernel mismatch found'
    return False


def statusMessage():
    uri = 'http://%s/status-message.php?machine=%s&version=%s&build=%s' % (getFeedsUrl().split('/')[2],
     getBoxType(),
     getImageVersion(),
     getImageBuild())
    try:
        req = urllib2.Request(uri)
        d = urllib2.urlopen(req)
        message = d.read()
    except:
        print '[OnlineVersionCheck][statusMessage] %s could not be fetched' % uri
        return False

    if message:
        return message
    return False