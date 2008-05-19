#@+leo-ver=4-thin
#@+node:ekr.20031218072017.3603:@thin leoUndo.py
'''Undo manager.'''

#@@language python
#@@tabwidth -4
#@@pagewidth 80

#@<< How Leo implements unlimited undo >>
#@+node:ekr.20031218072017.2413:<< How Leo implements unlimited undo >>
#@+at
# 
# Think of the actions that may be Undone or Redone as a string of beads
# (g.Bunches) containing all information needed to undo _and_ redo an 
# operation.
# 
# A bead pointer points to the present bead. Undoing an operation moves the 
# bead
# pointer backwards; redoing an operation moves the bead pointer forwards. The
# bead pointer points in front of the first bead when Undo is disabled. The 
# bead
# pointer points at the last bead when Redo is disabled.
# 
# The Undo command uses the present bead to undo the action, then moves the 
# bead
# pointer backwards. The Redo command uses the bead after the present bead to 
# redo
# the action, then moves the bead pointer forwards. The list of beads does not
# branch; all undoable operations (except the Undo and Redo commands 
# themselves)
# delete any beads following the newly created bead.
# 
# New in Leo 4.3: User (client) code should call u.beforeX and u.afterX 
# methods to
# create a bead describing the operation that is being performed. (By 
# convention,
# the code sets u = c.undoer for undoable operations.) Most u.beforeX methods
# return 'undoData' that the client code merely passes to the corresponding
# u.afterX method. This data contains the 'before' snapshot. The u.afterX 
# methods
# then create a bead containing both the 'before' and 'after' snapshots.
# 
# New in Leo 4.3: u.beforeChangeGroup and u.afterChangeGroup allow multiple 
# calls
# to u.beforeX and u.afterX methods to be treated as a single undoable entry. 
# See
# the code for the Change All, Sort, Promote and Demote commands for examples.
# u.before/afterChangeGroup substantially reduce the number of u.before/afterX
# methods needed.
# 
# New in Leo 4.3: It would be possible for plugins or other code to define 
# their
# own u.before/afterX methods. Indeed, u.afterX merely needs to set the
# bunch.undoHelper and bunch.redoHelper ivars to the methods used to undo and 
# redo
# the operation. See the code for the various u.before/afterX methods for
# guidance.
# 
# New in Leo 4.3: p.setDirty and p.setAllAncestorAtFileNodesDirty now return a
# 'dirtyVnodeList' that all vnodes that became dirty as the result of an
# operation. More than one list may be generated: client code is responsible 
# for
# merging lists using the pattern dirtyVnodeList.extend(dirtyVnodeList2)
# 
# I first saw this model of unlimited undo in the documentation for Apple's 
# Yellow Box classes.
#@-at
#@-node:ekr.20031218072017.2413:<< How Leo implements unlimited undo >>
#@nl

import leo.core.leoGlobals as g
import string

#@+others
#@+node:ekr.20031218072017.3605:class undoer
class undoer:
    """A class that implements unlimited undo and redo."""
    #@    @+others
    #@+node:ekr.20031218072017.3606:undo.__init__ & clearIvars
    def __init__ (self,c):

        self.c = c
        self.debug = False # True: enable debugging code in new undo scheme.
        self.debug_print = False # True: enable print statements in debug code.

        self.granularity = c.config.getString('undo_granularity')
        if self.granularity: self.granularity = self.granularity.lower()
        if self.granularity not in ('node','line','word','char'):
            self.granularity = 'line'
        # g.trace('undoer',self.granularity)

        self.max_undo_stack_size = c.config.getInt('max_undo_stack_size') or 0

        # Statistics comparing old and new ways (only if self.debug is on).
        self.new_mem = 0
        self.old_mem = 0

        # State ivars...
        self.undoType = "Can't Undo"
        # These must be set here, _not_ in clearUndoState.
        self.redoMenuLabel = "Can't Redo"
        self.undoMenuLabel = "Can't Undo"
        self.realRedoMenuLabel = "Can't Redo"
        self.realUndoMenuLabel = "Can't Undo"
        self.undoing = False # True if executing an Undo command.
        self.redoing = False # True if executing a Redo command.

        # New in 4.2...
        self.optionalIvars = []

        # Set the following ivars to keep pychecker happy.
        self.afterTree = None
        self.beforeTree = None
        self.dirtyVnodeList = None
        self.kind = None
        self.newBack = None
        self.newBody = None
        self.newHead = None
        self.newMarked = None
        self.newN = None
        self.newP = None
        self.newParent = None
        self.newRecentFiles = None
        self.newTree = None
        self.oldBack = None
        self.oldBody = None
        self.oldHead = None
        self.oldMarked = None
        self.oldN = None
        self.oldParent = None
        self.oldRecentFiles = None
        self.oldTree = None
        self.pasteAsClone = None

    def redoHelper(self):
        pass

    def undoHelper(self):
        pass
    #@+node:ekr.20031218072017.3607:clearIvars
    def clearIvars (self):

        u = self

        u.p = None # The position/node being operated upon for undo and redo.

        for ivar in u.optionalIvars:
            setattr(u,ivar,None)
    #@-node:ekr.20031218072017.3607:clearIvars
    #@-node:ekr.20031218072017.3606:undo.__init__ & clearIvars
    #@+node:ekr.20050416092908.1:Internal helpers
    #@+node:ekr.20060127052111.1:cutStack
    def cutStack (self):

        u = self ; n = u.max_undo_stack_size

        if n > 0 and u.bead >= n and not g.app.unitTesting:

            # Do nothing if we are in the middle of creating a group.
            i = len(u.beads)-1
            while i >= 0:
                bunch = u.beads[i]
                if hasattr(bunch,'kind') and bunch.kind == 'beforeGroup':
                    return
                i -= 1

            # This work regardless of how many items appear after bead n.
            # g.trace('Cutting undo stack to %d entries' % (n))
            u.beads = u.beads[-n:]
            u.bead = n-1
            # g.trace('bead:',u.bead,'len(u.beads)',len(u.beads))
    #@-node:ekr.20060127052111.1:cutStack
    #@+node:EKR.20040526150818:getBead
    def getBead (self,n):

        '''Set undoer ivars from the bunch at the top of the undo stack.'''

        u = self
        if n < 0 or n >= len(u.beads):
            return None

        bunch = u.beads[n]

        self.setIvarsFromBunch(bunch)

        return bunch
    #@-node:EKR.20040526150818:getBead
    #@+node:EKR.20040526150818.1:peekBead
    def peekBead (self,n):

        u = self
        if n < 0 or n >= len(u.beads):
            return None
        bunch = u.beads[n]
        # g.trace(n,len(u.beads),bunch)
        return bunch
    #@-node:EKR.20040526150818.1:peekBead
    #@+node:ekr.20060127113243:pushBead
    def pushBead (self,bunch):

        u = self

        # New in 4.4b2:  Add this to the group if it is being accumulated.
        bunch2 = u.bead >= 0 and u.bead < len(u.beads) and u.beads[u.bead]

        if bunch2 and hasattr(bunch2,'kind') and bunch2.kind == 'beforeGroup':
            # Just append the new bunch the group's items.
            bunch2.items.append(bunch)
        else:
            # Push the bunch.
            u.bead += 1
            u.beads[u.bead:] = [bunch]
            # g.trace('u.bead',u.bead,'len u.beads',len(u.beads))

            # Recalculate the menu labels.
            u.setUndoTypes()
    #@-node:ekr.20060127113243:pushBead
    #@+node:ekr.20060127070008:setIvarsFromBunch
    def setIvarsFromBunch (self,bunch):

        u = self

        u.clearIvars()

        if 0: # Debugging.
            print '-' * 40
            keys = bunch.keys()
            keys.sort()
            for key in keys:
                g.trace(key,bunch.get(key))
            print '-' * 20

        for key in bunch.keys():
            val = bunch.get(key)
            # g.trace(key,val)
            setattr(u,key,val)
            if key not in u.optionalIvars:
                u.optionalIvars.append(key)
    #@-node:ekr.20060127070008:setIvarsFromBunch
    #@+node:ekr.20050126081529:recognizeStartOfTypingWord
    def recognizeStartOfTypingWord (self,
        old_lines,old_row,old_col,old_ch, 
        new_lines,new_row,new_col,new_ch):

        # __pychecker__ = '--no-argsused' # Ignore all unused arguments here.

        ''' A potentially user-modifiable method that should return True if the
        typing indicated by the params starts a new 'word' for the purposes of
        undo with 'word' granularity.

        u.setUndoTypingParams calls this method only when the typing could possibly
        continue a previous word. In other words, undo will work safely regardless
        of the value returned here.

        old_ch is the char at the given (Tk) row, col of old_lines.
        new_ch is the char at the given (Tk) row, col of new_lines.

        The present code uses only old_ch and new_ch. The other arguments are given
        for use by more sophisticated algorithms.'''

        # Start a word if new_ch begins whitespace + word
        return not old_ch.isspace() and new_ch.isspace()
    #@-node:ekr.20050126081529:recognizeStartOfTypingWord
    #@+node:ekr.20031218072017.3613:redoMenuName, undoMenuName
    def redoMenuName (self,name):

        if name=="Can't Redo":
            return name
        else:
            return "Redo " + name

    def undoMenuName (self,name):

        if name=="Can't Undo":
            return name
        else:
            return "Undo " + name
    #@-node:ekr.20031218072017.3613:redoMenuName, undoMenuName
    #@+node:ekr.20031218072017.3614:setRedoType, setUndoType
    # These routines update both the ivar and the menu label.
    def setRedoType (self,theType):
        # g.trace(theType,g.callers())
        u = self ; frame = u.c.frame

        if type(theType) != type(''):
            g.trace('oops: expected string for command, got %s' % repr(theType))
            g.trace(g.callers())
            theType = '<unknown>'

        menu = frame.menu.getMenu("Edit")
        name = u.redoMenuName(theType)
        if name != u.redoMenuLabel:
            # Update menu using old name.
            realLabel = frame.menu.getRealMenuName(name)
            if realLabel == name:
                underline=g.choose(g.match(name,0,"Can't"),-1,0)
            else:
                underline = realLabel.find("&")
            realLabel = realLabel.replace("&","")
            frame.menu.setMenuLabel(menu,u.realRedoMenuLabel,realLabel,underline=underline)
            u.redoMenuLabel = name
            u.realRedoMenuLabel = realLabel

    def setUndoType (self,theType):
        # g.trace(theType,g.callers())

        u = self ; frame = u.c.frame
        if type(theType) != type(''):
            g.trace('oops: expected string for command, got %s' % repr(theType))
            g.trace(g.callers())
            theType = '<unknown>'
        menu = frame.menu.getMenu("Edit")
        name = u.undoMenuName(theType)
        if name != u.undoMenuLabel:
            # Update menu using old name.
            realLabel = frame.menu.getRealMenuName(name)
            if realLabel == name:
                underline=g.choose(g.match(name,0,"Can't"),-1,0)
            else:
                underline = realLabel.find("&")
            realLabel = realLabel.replace("&","")
            frame.menu.setMenuLabel(menu,u.realUndoMenuLabel,realLabel,underline=underline)
            u.undoType = theType
            u.undoMenuLabel = name
            u.realUndoMenuLabel = realLabel
    #@-node:ekr.20031218072017.3614:setRedoType, setUndoType
    #@+node:ekr.20031218072017.3616:setUndoTypes
    def setUndoTypes (self):

        u = self

        # g.trace(g.callers(7))

        # Set the undo type and undo menu label.
        bunch = u.peekBead(u.bead)
        if bunch:
            # g.trace(u.bead,len(u.beads),bunch.undoType)
            u.setUndoType(bunch.undoType)
        else:
            # g.trace(u.bead,len(u.beads))
            u.setUndoType("Can't Undo")

        # Set only the redo menu label.
        bunch = u.peekBead(u.bead+1)
        if bunch:
            u.setRedoType(bunch.undoType)
        else:
            u.setRedoType("Can't Redo")

        u.cutStack()
    #@-node:ekr.20031218072017.3616:setUndoTypes
    #@+node:EKR.20040530121329:u.restoreTree & helpers
    def restoreTree (self,treeInfo):

        """Use the tree info to restore all vnode and tnode data,
        including all links."""

        u = self

        # This effectively relinks all vnodes.
        for v,vInfo,tInfo in treeInfo:
            u.restoreVnodeUndoInfo(vInfo)
            u.restoreTnodeUndoInfo(tInfo)
    #@+node:ekr.20050415170737.2:restoreVnodeUndoInfo
    def restoreVnodeUndoInfo (self,bunch):

        """Restore all ivars saved in the bunch."""

        v = bunch.v

        v.statusBits = bunch.statusBits
        v.t.children = bunch.children
        v.parents    = bunch.parents

        uA = bunch.get('unknownAttributes')
        if uA is not None:
            v.unknownAttributes = uA
            v._p_changed = 1
    #@-node:ekr.20050415170737.2:restoreVnodeUndoInfo
    #@+node:ekr.20050415170812.2:restoreTnodeUndoInfo
    def restoreTnodeUndoInfo (self,bunch):

        t = bunch.t

        t._headString  = bunch.headString
        t._bodyString  = bunch.bodyString
        t.vnodeList   = bunch.vnodeList
        t.statusBits  = bunch.statusBits

        uA = bunch.get('unknownAttributes')
        if uA is not None:
            t.unknownAttributes = uA
            t._p_changed = 1
    #@-node:ekr.20050415170812.2:restoreTnodeUndoInfo
    #@-node:EKR.20040530121329:u.restoreTree & helpers
    #@+node:EKR.20040528075307:u.saveTree & helpers
    def saveTree (self,p,treeInfo=None):

        """Return a list of tuples with all info needed to handle a general undo operation."""

        # WARNING: read this before doing anything "clever"
        #@    << about u.saveTree >>
        #@+node:EKR.20040530114124:<< about u.saveTree >>
        #@+at 
        # The old code made a free-standing copy of the tree using v.copy and 
        # t.copy.  This looks "elegant" and is WRONG.  The problem is that it 
        # can not handle clones properly, especially when some clones were in 
        # the "undo" tree and some were not.   Moreover, it required complex 
        # adjustments to t.vnodeLists.
        # 
        # Instead of creating new nodes, the new code creates all information 
        # needed to properly restore the vnodes and tnodes.  It creates a list 
        # of tuples, on tuple for each vnode in the tree.  Each tuple has the 
        # form,
        # 
        # (vnodeInfo, tnodeInfo)
        # 
        # where vnodeInfo and tnodeInfo are dicts contain all info needed to 
        # recreate the nodes.  The v.createUndoInfoDict and 
        # t.createUndoInfoDict methods correspond to the old v.copy and t.copy 
        # methods.
        # 
        # Aside:  Prior to 4.2 Leo used a scheme that was equivalent to the 
        # createUndoInfoDict info, but quite a bit uglier.
        #@-at
        #@-node:EKR.20040530114124:<< about u.saveTree >>
        #@nl

        u = self ; topLevel = (treeInfo == None)
        if topLevel: treeInfo = []

        # Add info for p.v and p.v.t.  Duplicate tnode info is harmless.
        data = (p.v,u.createVnodeUndoInfo(p.v),u.createTnodeUndoInfo(p.v.t))
        treeInfo.append(data)

        # Recursively add info for the subtree.
        child = p.firstChild()
        while child:
            self.saveTree(child,treeInfo)
            child = child.next()

        # if topLevel: g.trace(treeInfo)
        return treeInfo
    #@+node:ekr.20050415170737.1:createVnodeUndoInfo
    def createVnodeUndoInfo (self,v):

        """Create a bunch containing all info needed to recreate a vnode for undo."""

        bunch = g.Bunch(
            v = v,
            statusBits = v.statusBits,
            parents    = v.parents[:],
            children   = v.t.children[:],
            # The tnode never changes so there is no need to save it here.
        )

        if hasattr(v,'unknownAttributes'):
            bunch.unknownAttributes = v.unknownAttributes

        return bunch
    #@-node:ekr.20050415170737.1:createVnodeUndoInfo
    #@+node:ekr.20050415170812.1:createTnodeUndoInfo
    def createTnodeUndoInfo (self,t):

        """Create a bunch containing all info needed to recreate a vnode."""

        bunch = g.Bunch(
            t = t,
            headString = t._headString,
            bodyString = t._bodyString,
            vnodeList  = t.vnodeList[:],
            statusBits = t.statusBits,
        )

        if hasattr(t,'unknownAttributes'):
            bunch.unknownAttributes = t.unknownAttributes

        return bunch
    #@-node:ekr.20050415170812.1:createTnodeUndoInfo
    #@-node:EKR.20040528075307:u.saveTree & helpers
    #@+node:ekr.20050525151449:u.trace
    def trace (self):

        ivars = ('kind','undoType')

        for ivar in ivars:
            print ivar, getattr(self,ivar)
    #@-node:ekr.20050525151449:u.trace
    #@+node:ekr.20050410095424:updateMarks
    def updateMarks (self,oldOrNew):

        '''Update dirty and marked bits.'''

        u = self ; c = u.c

        if oldOrNew not in ('new','old'):
            g.trace("can't happen")
            return

        isOld = oldOrNew=='old'
        marked = g.choose(isOld,u.oldMarked, u.newMarked)

        if marked:  c.setMarked(u.p)
        else:       c.clearMarked(u.p)

        # Bug fix: Leo 4.4.6: Undo/redo always set changed/dirty bits
        # because the file may have been saved.
        u.p.setDirty(setDescendentsDirty=False)
        u.p.setAllAncestorAtFileNodesDirty(setDescendentsDirty=False) # Bug fix: Leo 4.4.6
        u.c.setChanged(True)
    #@-node:ekr.20050410095424:updateMarks
    #@-node:ekr.20050416092908.1:Internal helpers
    #@+node:ekr.20031218072017.3608:Externally visible entries
    #@+node:ekr.20050318085432.4:afterX...
    #@+node:ekr.20050315134017.4:afterChangeGroup
    def afterChangeGroup (self,p,undoType,reportFlag=False,dirtyVnodeList=[]):

        '''Create an undo node for general tree operations using d created by beforeChangeTree'''

        u = self ; c = self.c ; w = c.frame.body.bodyCtrl
        if u.redoing or u.undoing: return

        # g.trace('u.bead',u.bead,'len u.beads',len(u.beads))

        bunch = u.beads[u.bead]
        if bunch.kind == 'beforeGroup':
            bunch.kind = 'afterGroup'
        else:
            g.trace('oops: expecting beforeGroup, got %s' % bunch.kind)

        # Set the types & helpers.
        bunch.kind = 'afterGroup'
        bunch.undoType = undoType

        # Set helper only for undo:
        # The bead pointer will point to an 'beforeGroup' bead for redo.
        bunch.undoHelper = u.undoGroup
        bunch.redoHelper = u.redoGroup

        bunch.dirtyVnodeList = dirtyVnodeList

        bunch.newP = p.copy()
        bunch.newSel = w.getSelectionRange()

        # Tells whether to report the number of separate changes undone/redone.
        bunch.reportFlag = reportFlag

        if 0:
            # Push the bunch.
            u.bead += 1
            u.beads[u.bead:] = [bunch]

        # Recalculate the menu labels.
        u.setUndoTypes()

        # g.trace(u.undoMenuLabel,u.redoMenuLabel)
    #@-node:ekr.20050315134017.4:afterChangeGroup
    #@+node:ekr.20050315134017.2:afterChangeNodeContents
    def afterChangeNodeContents (self,p,command,bunch,dirtyVnodeList=[]):

        '''Create an undo node using d created by beforeChangeNode.'''

        u = self ; c = self.c ; w = c.frame.body.bodyCtrl
        if u.redoing or u.undoing: return

        # Set the type & helpers.
        bunch.kind = 'node'
        bunch.undoType = command
        bunch.undoHelper = u.undoNodeContents
        bunch.redoHelper = u.redoNodeContents

        bunch.dirtyVnodeList = dirtyVnodeList

        bunch.newBody = p.bodyString()
        bunch.newChanged = u.c.isChanged()
        bunch.newDirty = p.isDirty()
        bunch.newHead = p.headString()
        bunch.newMarked = p.isMarked()
        bunch.newSel = w.getSelectionRange()

        u.pushBead(bunch)
    #@-node:ekr.20050315134017.2:afterChangeNodeContents
    #@+node:ekr.20050315134017.3:afterChangeTree
    def afterChangeTree (self,p,command,bunch):

        '''Create an undo node for general tree operations using d created by beforeChangeTree'''

        u = self ; c = self.c ; w = c.frame.body.bodyCtrl
        if u.redoing or u.undoing: return

        # Set the types & helpers.
        bunch.kind = 'tree'
        bunch.undoType = command
        bunch.undoHelper = u.undoTree
        bunch.redoHelper = u.redoTree

        # Set by beforeChangeTree: changed, oldSel, oldText, oldTree, p
        bunch.newSel = w.getSelectionRange()
        bunch.newText = w.getAllText()
        bunch.newTree = u.saveTree(p)

        u.pushBead(bunch)
    #@-node:ekr.20050315134017.3:afterChangeTree
    #@+node:ekr.20050424161505:afterClearRecentFiles
    def afterClearRecentFiles (self,bunch):

        u = self

        bunch.newRecentFiles = g.app.config.recentFiles[:]

        bunch.undoType = 'Clear Recent Files'
        bunch.undoHelper = u.undoClearRecentFiles
        bunch.redoHelper = u.redoClearRecentFiles

        u.pushBead(bunch)

        return bunch
    #@-node:ekr.20050424161505:afterClearRecentFiles
    #@+node:ekr.20050411193627.5:afterCloneNode
    def afterCloneNode (self,p,command,bunch,dirtyVnodeList=[]):

        u = self ; c = u.c
        if u.redoing or u.undoing: return

        # Set types & helpers
        bunch.kind = 'clone'
        bunch.undoType = command

        # Set helpers
        bunch.undoHelper = u.undoCloneNode
        bunch.redoHelper = u.redoCloneNode

        bunch.newBack = p.back() # 6/15/05
        bunch.newParent = p.parent() # 6/15/05

        bunch.newP = p.copy()
        bunch.dirtyVnodeList = dirtyVnodeList

        bunch.newChanged = c.isChanged()
        bunch.newDirty = p.isDirty()
        bunch.newMarked = p.isMarked()

        u.pushBead(bunch)
    #@-node:ekr.20050411193627.5:afterCloneNode
    #@+node:ekr.20050411193627.6:afterDehoist
    def afterDehoist (self,p,command):

        u = self
        if u.redoing or u.undoing: return

        bunch = u.createCommonBunch(p)

        # Set types & helpers
        bunch.kind = 'dehoist'
        bunch.undoType = command

        # Set helpers
        bunch.undoHelper = u.undoDehoistNode
        bunch.redoHelper = u.redoDehoistNode

        u.pushBead(bunch)
    #@-node:ekr.20050411193627.6:afterDehoist
    #@+node:ekr.20050411193627.8:afterDeleteNode
    def afterDeleteNode (self,p,command,bunch,dirtyVnodeList=[]):

        u = self ; c = u.c
        if u.redoing or u.undoing: return

        # Set types & helpers
        bunch.kind = 'delete'
        bunch.undoType = command

        # Set helpers
        bunch.undoHelper = u.undoDeleteNode
        bunch.redoHelper = u.redoDeleteNode

        bunch.newP = p.copy()
        bunch.dirtyVnodeList = dirtyVnodeList

        bunch.newChanged = c.isChanged()
        bunch.newDirty = p.isDirty()
        bunch.newMarked = p.isMarked()

        u.pushBead(bunch)
    #@-node:ekr.20050411193627.8:afterDeleteNode
    #@+node:ekr.20080425060424.8:afterDemote
    def afterDemote (self,p,followingSibs,dirtyVnodeList):

        '''Create an undo node for demote operations.'''

        u = self
        bunch = u.createCommonBunch(p)

        # Set types.
        bunch.kind = 'demote'
        bunch.undoType = 'Demote'

        bunch.undoHelper = u.undoDemote
        bunch.redoHelper = u.redoDemote

        bunch.followingSibs = followingSibs

        # Push the bunch.
        u.bead += 1
        u.beads[u.bead:] = [bunch]

        # Recalculate the menu labels.
        u.setUndoTypes()
    #@-node:ekr.20080425060424.8:afterDemote
    #@+node:ekr.20050411193627.7:afterHoist
    def afterHoist (self,p,command):

        u = self
        if u.redoing or u.undoing: return

        bunch = u.createCommonBunch(p)

        # Set types & helpers
        bunch.kind = 'hoist'
        bunch.undoType = command

        # Set helpers
        bunch.undoHelper = u.undoHoistNode
        bunch.redoHelper = u.redoHoistNode

        u.pushBead(bunch)
    #@-node:ekr.20050411193627.7:afterHoist
    #@+node:ekr.20050411193627.9:afterInsertNode
    def afterInsertNode (self,p,command,bunch,dirtyVnodeList=[]):

        u = self ; c = u.c
        if u.redoing or u.undoing: return

        # Set types & helpers
        bunch.kind = 'insert'
        bunch.undoType = command
        # g.trace(repr(command),g.callers())

        # Set helpers
        bunch.undoHelper = u.undoInsertNode
        bunch.redoHelper = u.redoInsertNode

        bunch.newP = p.copy()
        bunch.dirtyVnodeList = dirtyVnodeList

        bunch.newBack = p.back()
        bunch.newParent = p.parent()

        bunch.newChanged = c.isChanged()
        bunch.newDirty = p.isDirty()
        bunch.newMarked = p.isMarked()

        if bunch.pasteAsClone:
            beforeTree=bunch.beforeTree
            afterTree = []
            for bunch2 in beforeTree:
                t = bunch2.t
                afterTree.append(
                    g.Bunch(t=t,head=t._headString[:],body=t._bodyString[:]))
            bunch.afterTree=afterTree
            # g.trace(afterTree)

        u.pushBead(bunch)
    #@-node:ekr.20050411193627.9:afterInsertNode
    #@+node:ekr.20050526124257:afterMark
    def afterMark (self,p,command,bunch,dirtyVnodeList=[]):

        '''Create an undo node for mark and unmark commands.'''

        # __pychecker__ = '--no-argsused'
            # 'command' unused, but present for compatibility with similar methods.

        u = self
        if u.redoing or u.undoing: return

        # Set the type & helpers.
        bunch.undoHelper = u.undoMark
        bunch.redoHelper = u.redoMark

        bunch.dirtyVnodeList = dirtyVnodeList
        bunch.newChanged = u.c.isChanged()
        bunch.newDirty = p.isDirty()
        bunch.newMarked = p.isMarked()

        u.pushBead(bunch)
    #@-node:ekr.20050526124257:afterMark
    #@+node:ekr.20050410110343:afterMoveNode
    def afterMoveNode (self,p,command,bunch,dirtyVnodeList=[]):

        u = self ; c = u.c
        if u.redoing or u.undoing: return

        # Set the types & helpers.
        bunch.kind = 'move'
        bunch.undoType = command

        # Set helper only for undo:
        # The bead pointer will point to an 'beforeGroup' bead for redo.
        bunch.undoHelper = u.undoMove
        bunch.redoHelper = u.redoMove

        bunch.dirtyVnodeList = dirtyVnodeList

        bunch.newChanged = c.isChanged()
        bunch.newDirty = p.isDirty()
        bunch.newMarked = p.isMarked()

        # bunch.newBack   = p.back()
        # bunch.newParent = p.parent()
        bunch.newN = p.childIndex()
        bunch.newParent_v = p._parentVnode()
        bunch.newP = p.copy()

        u.pushBead(bunch)
    #@-node:ekr.20050410110343:afterMoveNode
    #@+node:ekr.20080425060424.12:afterPromote
    def afterPromote (self,p,children,dirtyVnodeList):

        '''Create an undo node for demote operations.'''

        u = self
        bunch = u.createCommonBunch(p)

        # Set types.
        bunch.kind = 'promote'
        bunch.undoType = 'Promote'

        bunch.undoHelper = u.undoPromote
        bunch.redoHelper = u.redoPromote

        bunch.children = children

        # Push the bunch.
        u.bead += 1
        u.beads[u.bead:] = [bunch]

        # Recalculate the menu labels.
        u.setUndoTypes()
    #@-node:ekr.20080425060424.12:afterPromote
    #@+node:ekr.20080425060424.2:afterSort
    def afterSort (self,p,bunch,dirtyVnodeList):

        '''Create an undo node for sort operations'''

        u = self ; c = self.c
        if u.redoing or u.undoing: return

        bunch.dirtyVnodeList = dirtyVnodeList

        # Recalculate the menu labels.
        u.setUndoTypes()

        # g.trace(u.undoMenuLabel,u.redoMenuLabel)
    #@-node:ekr.20080425060424.2:afterSort
    #@-node:ekr.20050318085432.4:afterX...
    #@+node:ekr.20050318085432.3:beforeX...
    #@+node:ekr.20050315134017.7:beforeChangeGroup
    def beforeChangeGroup (self,p,command):

        u = self
        bunch = u.createCommonBunch(p)

        # Set types.
        bunch.kind = 'beforeGroup'
        bunch.undoType = command

        # Set helper only for redo:
        # The bead pointer will point to an 'afterGroup' bead for undo.
        bunch.undoHelper = u.undoGroup
        bunch.redoHelper = u.redoGroup
        bunch.items = []

        # Push the bunch.
        u.bead += 1
        u.beads[u.bead:] = [bunch]
    #@-node:ekr.20050315134017.7:beforeChangeGroup
    #@+node:ekr.20050315133212.2:beforeChangeNodeContents
    def beforeChangeNodeContents (self,p,oldBody=None,oldHead=None):

        '''Return data that gets passed to afterChangeNode'''

        u = self

        bunch = u.createCommonBunch(p)

        bunch.oldBody = oldBody or p.bodyString()
        bunch.oldHead = oldHead or p.headString()

        return bunch
    #@-node:ekr.20050315133212.2:beforeChangeNodeContents
    #@+node:ekr.20050315134017.6:beforeChangeTree
    def beforeChangeTree (self,p):

        # g.trace(p.headString())

        u = self ; c = u.c ; w = c.frame.body.bodyCtrl

        bunch = u.createCommonBunch(p)
        bunch.oldSel = w.getSelectionRange()
        bunch.oldText = w.getAllText()
        bunch.oldTree = u.saveTree(p)

        return bunch
    #@-node:ekr.20050315134017.6:beforeChangeTree
    #@+node:ekr.20050424161505.1:beforeClearRecentFiles
    def beforeClearRecentFiles (self):

        u = self ; p = u.c.currentPosition()

        bunch = u.createCommonBunch(p)
        bunch.oldRecentFiles = g.app.config.recentFiles[:]

        return bunch
    #@-node:ekr.20050424161505.1:beforeClearRecentFiles
    #@+node:ekr.20050412080354:beforeCloneNode
    def beforeCloneNode (self,p):

        u = self

        bunch = u.createCommonBunch(p)

        return bunch
    #@-node:ekr.20050412080354:beforeCloneNode
    #@+node:ekr.20050411193627.3:beforeDeleteNode
    def beforeDeleteNode (self,p):

        u = self

        bunch = u.createCommonBunch(p)

        bunch.oldBack = p.back()
        bunch.oldParent = p.parent()

        return bunch
    #@-node:ekr.20050411193627.3:beforeDeleteNode
    #@+node:ekr.20050411193627.4:beforeInsertNode
    def beforeInsertNode (self,p,pasteAsClone=False,copiedBunchList=[]):

        u = self

        bunch = u.createCommonBunch(p)
        bunch.pasteAsClone = pasteAsClone

        if pasteAsClone:
            # Save the list of bunched.
            bunch.beforeTree = copiedBunchList
            # g.trace(bunch.beforeTree)

        return bunch
    #@-node:ekr.20050411193627.4:beforeInsertNode
    #@+node:ekr.20050526131252:beforeMark
    def beforeMark (self,p,command):

        u = self
        bunch = u.createCommonBunch(p)

        bunch.kind = 'mark'
        bunch.undoType = command

        return bunch
    #@-node:ekr.20050526131252:beforeMark
    #@+node:ekr.20050410110215:beforeMoveNode
    def beforeMoveNode (self,p):

        u = self

        bunch = u.createCommonBunch(p)

        # bunch.oldBack = p.back()
        # bunch.oldParent = p.parent()
        bunch.oldN = p.childIndex()
        bunch.oldParent_v = p._parentVnode()

        return bunch
    #@-node:ekr.20050410110215:beforeMoveNode
    #@+node:ekr.20080425060424.3:beforeSort
    def beforeSort (self,p,undoType,oldChildren,newChildren,sortChildren):

        '''Create an undo node for sort operations.'''

        u = self
        bunch = u.createCommonBunch(p)

        # Set types.
        bunch.kind = 'sort'
        bunch.undoType = undoType

        bunch.undoHelper = u.undoSort
        bunch.redoHelper = u.redoSort

        bunch.oldChildren = oldChildren
        bunch.newChildren = newChildren
        bunch.sortChildren = sortChildren # A bool

        # Push the bunch.
        u.bead += 1
        u.beads[u.bead:] = [bunch]

        return bunch
    #@-node:ekr.20080425060424.3:beforeSort
    #@+node:ekr.20050318085432.2:createCommonBunch
    def createCommonBunch (self,p):

        '''Return a bunch containing all common undo info.
        This is mostly the info for recreating an empty node at position p.'''

        u = self ; c = u.c ; w = c.frame.body.bodyCtrl

        return g.Bunch(
            oldChanged = c.isChanged(),
            oldDirty = p.isDirty(),
            oldMarked = p.isMarked(),
            oldSel = w.getSelectionRange(),
            p = p.copy(),
        )
    #@-node:ekr.20050318085432.2:createCommonBunch
    #@-node:ekr.20050318085432.3:beforeX...
    #@+node:ekr.20031218072017.3610:canRedo & canUndo
    # Translation does not affect these routines.

    def canRedo (self):

        u = self

        return u.redoMenuLabel != "Can't Redo"

    def canUndo (self):

        u = self

        return u.undoMenuLabel != "Can't Undo"
    #@-node:ekr.20031218072017.3610:canRedo & canUndo
    #@+node:ekr.20031218072017.3609:clearUndoState
    def clearUndoState (self):

        """Clears then entire Undo state.

        All non-undoable commands should call this method."""

        u = self
        u.setRedoType("Can't Redo")
        u.setUndoType("Can't Undo")
        u.beads = [] # List of undo nodes.
        u.bead = -1 # Index of the present bead: -1:len(beads)
        u.clearIvars()
    #@-node:ekr.20031218072017.3609:clearUndoState
    #@+node:ekr.20031218072017.3611:enableMenuItems
    def enableMenuItems (self):

        u = self ; frame = u.c.frame

        menu = frame.menu.getMenu("Edit")
        frame.menu.enableMenu(menu,u.redoMenuLabel,u.canRedo())
        frame.menu.enableMenu(menu,u.undoMenuLabel,u.canUndo())
    #@-node:ekr.20031218072017.3611:enableMenuItems
    #@+node:ekr.20050525151217:getMark & rollbackToMark (no longer used)
    if 0:
        def getMark (self):

            # __pychecker__ = '--no-classattr' # self.bead does, in fact, exist.

            return self.bead

        def rollbackToMark (self,n):

            u = self

            u.bead = n
            u.beads = u.beads[:n+1]
            u.setUndoTypes()

        rollBackToMark = rollbackToMark
    #@-node:ekr.20050525151217:getMark & rollbackToMark (no longer used)
    #@+node:ekr.20031218072017.1490:setUndoTypingParams
    def setUndoTypingParams (self,p,undo_type,oldText,newText,oldSel,newSel,oldYview=None):

        # __pychecker__ = 'maxlines=2000' # Ignore the size of this method.

        '''Save enough information so a typing operation can be undone and redone.

        Do nothing when called from the undo/redo logic because the Undo and Redo commands merely reset the bead pointer.'''

        u = self ; c = u.c
        trace = False # Can cause unit tests to fail.
        #@    << return if there is nothing to do >>
        #@+node:ekr.20040324061854:<< return if there is nothing to do >>
        if u.redoing or u.undoing:
            return None

        if undo_type == None:
            return None

        if undo_type == "Can't Undo":
            u.clearUndoState()
            u.setUndoTypes() # Must still recalculate the menu labels.
            return None

        if oldText == newText:
            # g.trace("no change")
            u.setUndoTypes() # Must still recalculate the menu labels.
            return None
        #@-node:ekr.20040324061854:<< return if there is nothing to do >>
        #@nl
        # g.trace(undo_type,g.callers(7))
        #@    << init the undo params >>
        #@+node:ekr.20040324061854.1:<< init the undo params >>
        # Clear all optional params.
        for ivar in u.optionalIvars:
            setattr(u,ivar,None)

        # Set the params.
        u.undoType = undo_type
        u.p = p.copy()
        #@-node:ekr.20040324061854.1:<< init the undo params >>
        #@nl
        #@    << compute leading, middle & trailing  lines >>
        #@+node:ekr.20031218072017.1491:<< compute leading, middle & trailing  lines >>
        #@+at
        # Incremental undo typing is similar to incremental syntax coloring. 
        # We compute
        # the number of leading and trailing lines that match, and save both 
        # the old and
        # new middle lines. NB: the number of old and new middle lines may be 
        # different.
        #@-at
        #@@c

        old_lines = string.split(oldText,'\n')
        new_lines = string.split(newText,'\n')
        new_len = len(new_lines)
        old_len = len(old_lines)
        min_len = min(old_len,new_len)

        i = 0
        while i < min_len:
            if old_lines[i] != new_lines[i]:
                break
            i += 1
        leading = i

        if leading == new_len:
            # This happens when we remove lines from the end.
            # The new text is simply the leading lines from the old text.
            trailing = 0
        else:
            i = 0
            while i < min_len - leading:
                if old_lines[old_len-i-1] != new_lines[new_len-i-1]:
                    break
                i += 1
            trailing = i

        # NB: the number of old and new middle lines may be different.
        if trailing == 0:
            old_middle_lines = old_lines[leading:]
            new_middle_lines = new_lines[leading:]
        else:
            old_middle_lines = old_lines[leading:-trailing]
            new_middle_lines = new_lines[leading:-trailing]

        # Remember how many trailing newlines in the old and new text.
        i = len(oldText) - 1 ; old_newlines = 0
        while i >= 0 and oldText[i] == '\n':
            old_newlines += 1
            i -= 1

        i = len(newText) - 1 ; new_newlines = 0
        while i >= 0 and newText[i] == '\n':
            new_newlines += 1
            i -= 1

        if trace:
            print "lead,trail",leading,trailing
            print "old mid,nls:",len(old_middle_lines),old_newlines,oldText
            print "new mid,nls:",len(new_middle_lines),new_newlines,newText
            #print "lead,trail:",leading,trailing
            #print "old mid:",old_middle_lines
            #print "new mid:",new_middle_lines
            print "---------------------"
        #@-node:ekr.20031218072017.1491:<< compute leading, middle & trailing  lines >>
        #@nl
        #@    << save undo text info >>
        #@+node:ekr.20031218072017.1492:<< save undo text info >>
        #@+at 
        #@nonl
        # This is the start of the incremental undo algorithm.
        # 
        # We must save enough info to do _both_ of the following:
        # 
        # Undo: Given newText, recreate oldText.
        # Redo: Given oldText, recreate oldText.
        # 
        # The "given" texts for the undo and redo routines are simply 
        # p.bodyString().
        #@-at
        #@@c

        if u.debug:
            # Remember the complete text for comparisons...
            u.oldText = oldText
            u.newText = newText
            # Compute statistics comparing old and new ways...
            # The old doesn't often store the old text, so don't count it here.
            u.old_mem += len(newText)
            s1 = string.join(old_middle_lines,'\n')
            s2 = string.join(new_middle_lines,'\n')
            u.new_mem += len(s1) + len(s2)
        else:
            u.oldText = None
            u.newText = None

        u.leading = leading
        u.trailing = trailing
        u.oldMiddleLines = old_middle_lines
        u.newMiddleLines = new_middle_lines
        u.oldNewlines = old_newlines
        u.newNewlines = new_newlines
        #@-node:ekr.20031218072017.1492:<< save undo text info >>
        #@nl
        #@    << save the selection and scrolling position >>
        #@+node:ekr.20040324061854.2:<< save the selection and scrolling position >>
        #Remember the selection.
        u.oldSel = oldSel
        u.newSel = newSel

        # Remember the scrolling position.
        if oldYview:
            u.yview = oldYview
        else:
            u.yview = c.frame.body.getYScrollPosition()
        #@-node:ekr.20040324061854.2:<< save the selection and scrolling position >>
        #@nl
        #@    << adjust the undo stack, clearing all forward entries >>
        #@+node:ekr.20040324061854.3:<< adjust the undo stack, clearing all forward entries >>
        #@+at 
        #@nonl
        # New in Leo 4.3. Instead of creating a new bead on every character, 
        # we may adjust the top bead:
        # 
        # word granularity: adjust the top bead if the typing would continue 
        # the word.
        # line granularity: adjust the top bead if the typing is on the same 
        # line.
        # node granularity: adjust the top bead if the typing is anywhere on 
        # the same node.
        #@-at
        #@@c

        granularity = u.granularity

        old_d = u.peekBead(u.bead)
        old_p = old_d and old_d.get('p')

        #@<< set newBead if we can't share the previous bead >>
        #@+node:ekr.20050125220613:<< set newBead if we can't share the previous bead >>
        #@+at 
        #@nonl
        # We must set newBead to True if undo_type is not 'Typing' so that 
        # commands that
        # get treated like typing (by updateBodyPane and onBodyChanged) don't 
        # get lumped
        # with 'real' typing.
        #@-at
        #@@c
        # g.trace(granularity)
        if (
            not old_d or not old_p or
            old_p.v != p.v or
            old_d.get('kind') != 'typing' or
            old_d.get('undoType') != 'Typing' or
            undo_type != 'Typing'
        ):
            newBead = True # We can't share the previous node.
        elif granularity == 'char':
            newBead = True # This was the old way.
        elif granularity == 'node':
            newBead = False # Always replace previous bead.
        else:
            assert granularity in ('line','word')
            # Replace the previous bead if only the middle lines have changed.
            newBead = (
                old_d.get('leading',0)  != u.leading or 
                old_d.get('trailing',0) != u.trailing
            )
            if granularity == 'word' and not newBead:
                # Protect the method that may be changed by the user
                try:
                    #@            << set newBead if the change does not continue a word >>
                    #@+node:ekr.20050125203937:<< set newBead if the change does not continue a word >>
                    old_start,old_end = oldSel
                    new_start,new_end = newSel
                    # g.trace('new_start',new_start,'old_start',old_start)
                    if old_start != old_end or new_start != new_end:
                        # The new and old characters are not contiguous.
                        newBead = True
                    else:
                        old_row,old_col = old_start.split('.')
                        new_row,new_col = new_start.split('.')
                        old_row,old_col = int(old_row),int(old_col)
                        new_row,new_col = int(new_row),int(new_col)
                        old_lines = g.splitLines(oldText)
                        new_lines = g.splitLines(newText)
                        # g.trace('old',old_row,old_col,len(old_lines))
                        # g.trace('new',new_row,new_col,len(new_lines))
                        # Recognize backspace, del, etc. as contiguous.
                        if old_row != new_row or abs(old_col- new_col) != 1:
                            # The new and old characters are not contiguous.
                            newBead = True
                        elif old_col == 0 or new_col == 0:
                            pass # We have just inserted a line.
                        else:
                            old_s = old_lines[old_row-1]
                            new_s = new_lines[new_row-1]
                            # New in 4.3b2:
                            # Guard against invalid oldSel or newSel params.
                            if old_col-1 >= len(old_s) or new_col-1 >= len(new_s):
                                newBead = True
                            else:
                                # g.trace(new_col,len(new_s),repr(new_s))
                                # g.trace(repr(old_ch),repr(new_ch))
                                old_ch = old_s[old_col-1]
                                new_ch = new_s[new_col-1]
                                newBead = self.recognizeStartOfTypingWord(
                                    old_lines,old_row,old_col,old_ch,
                                    new_lines,new_row,new_col,new_ch)
                    #@-node:ekr.20050125203937:<< set newBead if the change does not continue a word >>
                    #@nl
                except Exception:
                    if 0:
                        g.trace('old_lines',old_lines)
                        g.trace('new_lines',new_lines)
                    g.es('exception in','setUndoRedoTypingParams',color='blue')
                    g.es_exception()
                    newBead = True
        #@-node:ekr.20050125220613:<< set newBead if we can't share the previous bead >>
        #@nl

        if newBead:
            # Push params on undo stack, clearing all forward entries.
            bunch = g.Bunch(
                p = p.copy(),
                kind='typing',
                undoType = undo_type,
                undoHelper=u.undoTyping,
                redoHelper=u.redoTyping,
                oldText=u.oldText,
                oldSel=u.oldSel,
                oldNewlines=u.oldNewlines,
                oldMiddleLines=u.oldMiddleLines,
            )
            u.pushBead(bunch)
        else:
            bunch = old_d

        bunch.dirtyVnodeList = p.setAllAncestorAtFileNodesDirty()

        # Bug fix: Leo 4.4.6: always add p to the list.
        bunch.dirtyVnodeList.append(p.copy())
        bunch.leading=u.leading
        bunch.trailing= u.trailing
        bunch.newNewlines=u.newNewlines
        bunch.newMiddleLines=u.newMiddleLines
        bunch.newSel=u.newSel
        bunch.newText=u.newText
        bunch.yview=u.yview
        #@-node:ekr.20040324061854.3:<< adjust the undo stack, clearing all forward entries >>
        #@nl
        return bunch
    #@-node:ekr.20031218072017.1490:setUndoTypingParams
    #@-node:ekr.20031218072017.3608:Externally visible entries
    #@+node:ekr.20031218072017.2030:redo & helpers...
    def redo (self,event=None):

        '''Redo the operation undone by the last undo.'''

        u = self ; c = u.c
        # g.trace(g.callers(7))

        if not u.canRedo():
            # g.trace('cant redo',u.undoMenuLabel,u.redoMenuLabel)
            return
        if not u.getBead(u.bead+1):
            g.trace('no bead') ; return
        if not c.currentPosition():
            g.trace('no current position') ; return

        # g.trace(u.undoType)
        # g.trace(u.bead+1,len(u.beads),u.peekBead(u.bead+1))
        u.redoing = True 
        u.groupCount = 0

        c.beginUpdate()
        try:
            c.endEditing()
            if u.redoHelper: u.redoHelper()
            else: g.trace('no redo helper for %s %s' % (u.kind,u.undoType))
        finally:
            c.frame.body.updateEditors() # New in Leo 4.4.8.
            if 0: # Don't do this: it interferes with selection ranges.
                # This strange code forces a recomputation of the root position.
                c.selectPosition(c.currentPosition())
            else:
                c.setCurrentPosition(c.currentPosition())
            c.setChanged(True)
            c.endUpdate()
            c.recolor_now()
            c.bodyWantsFocusNow()
            u.redoing = False
            u.bead += 1
            u.setUndoTypes()
    #@nonl
    #@+node:ekr.20050424170219:redoClearRecentFiles
    def redoClearRecentFiles (self):

        u = self ; c = u.c

        g.app.recentFiles = u.newRecentFiles[:]
        c.recentFiles = u.newRecentFiles[:]

        c.frame.menu.createRecentFilesMenuItems()
    #@-node:ekr.20050424170219:redoClearRecentFiles
    #@+node:ekr.20050412083057:redoCloneNode
    def redoCloneNode (self):

        u = self ; c = u.c

        if u.newBack:
            u.newP._linkAfter(u.newBack)
        elif u.newParent:
            u.newP._linkAsNthChild(u.newParent,0)
        else:
            oldRoot = c.rootPosition()
            u.newP._linkAsRoot(oldRoot)

        for v in u.dirtyVnodeList:
            v.t.setDirty()

        u.newP.v._computeParentsOfChildren()
        u.newP._parentVnode()._computeParentsOfChildren()

        c.selectPosition(u.newP)
    #@-node:ekr.20050412083057:redoCloneNode
    #@+node:EKR.20040526072519.2:redoDeleteNode
    def redoDeleteNode (self):

        u = self ; c = u.c

        c.selectPosition(u.p)
        c.deleteOutline()
        c.selectPosition(u.newP)
    #@-node:EKR.20040526072519.2:redoDeleteNode
    #@+node:ekr.20080425060424.9:redoDemote
    def redoDemote (self):

        u = self ; c = u.c
        parent_v = u.p._parentVnode()
        n = u.p.childIndex()

        # Remove the moved nodes from the parent's children.
        parent_v.t.children = parent_v.t.children[:n+1]

        # Add the moved nodes to p's children
        u.p.v.t.children.extend(u.followingSibs)

        # Adjust the parent links of all moved nodes.
        u.p.v._computeParentsOfChildren(children=u.followingSibs)

        c.setCurrentPosition(u.p)
    #@-node:ekr.20080425060424.9:redoDemote
    #@+node:ekr.20050318085432.6:redoGroup
    def redoGroup (self):

        '''Process beads until the matching 'afterGroup' bead is seen.'''

        u = self

        # Remember these values.
        c = u.c
        dirtyVnodeList = u.dirtyVnodeList or []
        newSel = u.newSel
        p = u.p.copy()

        u.groupCount += 1

        bunch = u.beads[u.bead] ; count = 0
        if not hasattr(bunch,'items'):
            g.trace('oops: expecting bunch.items.  bunch.kind = %s' % bunch.kind)
        else:
            c.beginUpdate()
            try:
                for z in bunch.items:
                    self.setIvarsFromBunch(z)
                    if z.redoHelper:
                        # g.trace(z.redoHelper)
                        z.redoHelper() ; count += 1
                    else:
                        g.trace('oops: no redo helper for %s' % u.undoType)
            finally:
                c.endUpdate(False)

        u.groupCount -= 1

        u.updateMarks('new') # Bug fix: Leo 4.4.6.

        for v in dirtyVnodeList:
            v.t.setDirty()

        if not g.unitTesting:
            g.es("redo",count,"instances")

        c.selectPosition(p)
        if newSel: c.frame.body.setSelectionRange(newSel)
    #@nonl
    #@-node:ekr.20050318085432.6:redoGroup
    #@+node:ekr.20050412085138.1:redoHoistNode & redoDehoistNode
    def redoHoistNode (self):

        u = self ; c = u.c

        c.selectPosition(u.p)
        c.hoist()

    def redoDehoistNode (self):

        u = self ; c = u.c

        c.selectPosition(u.p)
        c.dehoist()
    #@-node:ekr.20050412085138.1:redoHoistNode & redoDehoistNode
    #@+node:ekr.20050412084532:redoInsertNode
    def redoInsertNode (self):

        u = self ; c = u.c

        # g.trace('newP',u.newP.v,'back',u.newBack,'parent',u.newParent.v)

        if u.newBack:
            u.newP._linkAfter(u.newBack)
        elif u.newParent:
            u.newP._linkAsNthChild(u.newParent,0)
        else:
            oldRoot = c.rootPosition()
            u.newP._linkAsRoot(oldRoot)

        # Restore all vnodeLists (and thus all clone marks).
        u.newP._restoreLinksInTree()

        if u.pasteAsClone:
            for bunch in u.afterTree:
                t = bunch.t
                if u.newP.v.t == t:
                    c.setBodyString(u.newP,bunch.body)
                    c.setHeadString(u.newP,bunch.head)
                else:
                    t.setBodyString(bunch.body)
                    t.setHeadString(bunch.head)
                # g.trace(t,bunch.head,bunch.body)

        c.selectPosition(u.newP)
    #@-node:ekr.20050412084532:redoInsertNode
    #@+node:ekr.20050526125801:redoMark
    def redoMark (self):

        u = self ; c = u.c

        u.updateMarks('new')

        if u.groupCount == 0:

            for v in u.dirtyVnodeList:
                v.t.setDirty()

            c.selectPosition(u.p)
    #@nonl
    #@-node:ekr.20050526125801:redoMark
    #@+node:ekr.20050411111847:redoMove
    def redoMove (self):

        u = self ; c = u.c ; v = u.p.v
        assert(u.oldParent_v)
        assert(u.newParent_v)
        assert(v)

        # Adjust the children arrays.
        assert u.oldParent_v.t.children[u.oldN] == v
        del u.oldParent_v.t.children[u.oldN]
        u.newParent_v.t.children.insert(u.newN,v)

        # Recompute the parent links.
        u.newParent_v._computeParentsOfChildren()

        u.updateMarks('new')

        for v in u.dirtyVnodeList:
            v.t.setDirty()

        c.selectPosition(u.newP)
    #@-node:ekr.20050411111847:redoMove
    #@+node:ekr.20050318085432.7:redoNodeContents
    def redoNodeContents (self):

        u = self ; c = u.c ; w = c.frame.body.bodyCtrl

        # Restore the body.
        u.p.setBodyString(u.newBody)
        w.setAllText(u.newBody)
        c.frame.body.recolor(u.p,incremental=False)

        # Restore the headline.
        u.p.initHeadString(u.newHead)
        c.frame.tree.setHeadline(u.p,u.newHead) # New in 4.4b2.

        # g.trace('newHead',u.newHead,'revert',c.frame.tree.revertHeadline)

        if u.groupCount == 0 and u.newSel:
            u.c.frame.body.setSelectionRange(u.newSel)

        u.updateMarks('new')

        for v in u.dirtyVnodeList:
            v.t.setDirty()
    #@-node:ekr.20050318085432.7:redoNodeContents
    #@+node:ekr.20080425060424.13:redoPromote
    def redoPromote (self):

        u = self ; c = u.c
        parent_v = u.p._parentVnode()

        # Add the children to parent_v's children.
        n = u.p.childIndex() + 1
        z = parent_v.t.children[:]
        parent_v.t.children = z[:n]
        parent_v.t.children.extend(u.children)
        parent_v.t.children.extend(z[n:])

        # Remove v's children.
        u.p.v.t.children = []

        # Adjust the parent links of all moved nodes.
        parent_v._computeParentsOfChildren(children=u.children)

        c.setCurrentPosition(u.p)
    #@-node:ekr.20080425060424.13:redoPromote
    #@+node:ekr.20080425060424.4:redoSort
    def redoSort (self):

        u = self ; c = u.c

        parent_v = u.p._parentVnode()
        parent_v.t.children = u.newChildren
        c.setPositionAfterSort(u.sortChildren)
    #@nonl
    #@-node:ekr.20080425060424.4:redoSort
    #@+node:ekr.20050318085432.8:redoTree
    def redoTree (self):

        '''Redo replacement of an entire tree.'''

        u = self ; c = u.c

        u.p = self.undoRedoTree(u.p,u.oldTree,u.newTree)
        c.selectPosition(u.p) # Does full recolor.
        if u.newSel:
            c.frame.body.setSelectionRange(u.newSel)
    #@-node:ekr.20050318085432.8:redoTree
    #@+node:EKR.20040526075238.5:redoTyping
    def redoTyping (self):

        u = self ; c = u.c ; current = c.currentPosition()
        w = c.frame.body.bodyCtrl

        # selectPosition causes recoloring, so avoid if possible.
        if current != u.p:
            c.selectPosition(u.p)
        elif u.undoType in ('Cut','Paste','Clear Recent Files'):
            c.frame.body.forceFullRecolor()

        self.undoRedoText(
            u.p,u.leading,u.trailing,
            u.newMiddleLines,u.oldMiddleLines,
            u.newNewlines,u.oldNewlines,
            tag="redo",undoType=u.undoType)

        u.updateMarks('new')

        for v in u.dirtyVnodeList:
            v.t.setDirty()

        if u.newSel:
            c.bodyWantsFocusNow()
            i,j = u.newSel
            w.setSelectionRange(i,j,insert=j)
        if u.yview:
            c.bodyWantsFocusNow()
            c.frame.body.setYScrollPosition(u.yview)
    #@-node:EKR.20040526075238.5:redoTyping
    #@-node:ekr.20031218072017.2030:redo & helpers...
    #@+node:ekr.20031218072017.2039:undo & helpers...
    def undo (self,event=None):

        """Undo the operation described by the undo parameters."""

        u = self ; c = u.c
        # g.trace(g.callers(7))

        if not u.canUndo():
            # g.trace('cant undo',u.undoMenuLabel,u.redoMenuLabel)
            return
        if not u.getBead(u.bead):
            g.trace('no bead') ; return
        if not c.currentPosition():
            g.trace('no current position') ; return

        # g.trace(u.undoType)
        # g.trace(len(u.beads),u.bead,u.peekBead(u.bead))
        u.undoing = True
        u.groupCount = 0

        c.beginUpdate()
        try:
            c.endEditing()
            if u.undoHelper: u.undoHelper()
            else: g.trace('no undo helper for %s %s' % (u.kind,u.undoType))
        finally:
            c.frame.body.updateEditors() # New in Leo 4.4.8.
            if 0: # Don't do this: it interferes with selection ranges.
                # This strange code forces a recomputation of the root position.
                c.selectPosition(c.currentPosition())
            else:
                c.setCurrentPosition(c.currentPosition())
            c.setChanged(True)
            c.endUpdate()
            c.recolor_now()
            c.bodyWantsFocusNow()
            u.undoing = False
            u.bead -= 1
            u.setUndoTypes()
    #@nonl
    #@+node:ekr.20050424170219.1:undoClearRecentFiles
    def undoClearRecentFiles (self):

        u = self ; c = u.c

        g.app.recentFiles = u.oldRecentFiles[:]
        c.recentFiles = u.oldRecentFiles[:]

        c.frame.menu.createRecentFilesMenuItems()
    #@-node:ekr.20050424170219.1:undoClearRecentFiles
    #@+node:ekr.20050412083057.1:undoCloneNode
    def undoCloneNode (self):

        u = self ; c = u.c

        c.selectPosition(u.newP)
        c.deleteOutline()

        for v in u.dirtyVnodeList:
            v.t.setDirty() # Bug fix: Leo 4.4.6

        c.selectPosition(u.p)
    #@-node:ekr.20050412083057.1:undoCloneNode
    #@+node:ekr.20050412084055:undoDeleteNode
    def undoDeleteNode (self):

        u = self ; c = u.c

        if u.oldBack:
            u.p._linkAfter(u.oldBack)
        elif u.oldParent:
            u.p._linkAsNthChild(u.oldParent,0)
        else:
            oldRoot = c.rootPosition()
            u.p._linkAsRoot(oldRoot)

        # Restore all vnodeLists (and thus all clone marks).
        u.p._restoreLinksInTree()
        u.p.setAllAncestorAtFileNodesDirty()
        c.selectPosition(u.p)
    #@-node:ekr.20050412084055:undoDeleteNode
    #@+node:ekr.20080425060424.10:undoDemote
    def undoDemote (self):

        u = self ; c = u.c
        parent_v = u.p._parentVnode()
        n = len(u.followingSibs)

        # Remove the demoted nodes from p's children.
        u.p.v.t.children = u.p.v.t.children[:-n]

        # Add the demoted nodes to the parent's children.
        parent_v.t.children.extend(u.followingSibs)

        # Adjust the parent links of all moved nodes.
        parent_v._computeParentsOfChildren(children=u.followingSibs)

        c.setCurrentPosition(u.p)
    #@nonl
    #@-node:ekr.20080425060424.10:undoDemote
    #@+node:ekr.20050318085713:undoGroup
    def undoGroup (self):

        '''Process beads until the matching 'beforeGroup' bead is seen.'''

        u = self

        # Remember these values.
        c = u.c
        dirtyVnodeList = u.dirtyVnodeList or []
        oldSel = u.oldSel
        p = u.p.copy()

        u.groupCount += 1

        bunch = u.beads[u.bead] ; count = 0

        if not hasattr(bunch,'items'):
            g.trace('oops: expecting bunch.items.  bunch.kind = %s' % bunch.kind)
        else:
            # Important bug fix: 9/8/06: reverse the items first.
            reversedItems = bunch.items[:]
            reversedItems.reverse()
            c.beginUpdate()
            try:
                for z in reversedItems:
                    self.setIvarsFromBunch(z)
                    # g.trace(z.undoHelper)
                    if z.undoHelper:
                        z.undoHelper() ; count += 1
                    else:
                        g.trace('oops: no undo helper for %s' % u.undoType)
            finally:
                c.endUpdate(False)

        u.groupCount -= 1

        u.updateMarks('old') # Bug fix: Leo 4.4.6.

        for v in dirtyVnodeList:
            v.t.setDirty() # Bug fix: Leo 4.4.6.

        if not g.unitTesting:
            g.es("undo",count,"instances")

        c.selectPosition(p)
        if oldSel: c.frame.body.setSelectionRange(oldSel)
    #@nonl
    #@-node:ekr.20050318085713:undoGroup
    #@+node:ekr.20050412083244:undoHoistNode & undoDehoistNode
    def undoHoistNode (self):

        u = self ; c = u.c

        c.selectPosition(u.p)
        c.dehoist()

    def undoDehoistNode (self):

        u = self ; c = u.c

        c.selectPosition(u.p)
        c.hoist()
    #@-node:ekr.20050412083244:undoHoistNode & undoDehoistNode
    #@+node:ekr.20050412085112:undoInsertNode
    def undoInsertNode (self):

        u = self ; c = u.c

        c.selectPosition(u.newP)
        c.deleteOutline()

        if u.pasteAsClone:
            for bunch in u.beforeTree:
                t = bunch.t
                if u.p.v.t == t:
                    c.setBodyString(u.p,bunch.body)
                    c.setHeadString(u.p,bunch.head)
                else:
                    t.setBodyString(bunch.body)
                    t.setHeadString(bunch.head)

        c.selectPosition(u.p)
    #@-node:ekr.20050412085112:undoInsertNode
    #@+node:ekr.20050526124906:undoMark
    def undoMark (self):

        u = self ; c = u.c

        u.updateMarks('old')

        if u.groupCount == 0:

            for v in u.dirtyVnodeList:
                v.t.setDirty() # Bug fix: Leo 4.4.6.

            c.selectPosition(u.p)
    #@-node:ekr.20050526124906:undoMark
    #@+node:ekr.20050411112033:undoMove
    def undoMove (self):

        u = self ; c = u.c ; v = u.p.v
        assert(u.oldParent_v)
        assert(u.newParent_v)
        assert(v)

        # Adjust the children arrays.
        assert u.newParent_v.t.children[u.newN] == v
        del u.newParent_v.t.children[u.newN]
        u.oldParent_v.t.children.insert(u.oldN,v)

        # Recompute the parent links.
        u.oldParent_v._computeParentsOfChildren()

        u.updateMarks('old')

        for v in u.dirtyVnodeList:
            v.t.setDirty()

        c.selectPosition(u.p)
    #@-node:ekr.20050411112033:undoMove
    #@+node:ekr.20050318085713.1:undoNodeContents
    def undoNodeContents (self):

        '''Undo all changes to the contents of a node,
        including headline and body text, and marked bits.
        '''

        u = self ; c = u.c ;  w = c.frame.body.bodyCtrl

        u.p.setBodyString(u.oldBody)
        w.setAllText(u.oldBody)
        c.frame.body.recolor(u.p,incremental=False)

        u.p.initHeadString(u.oldHead)
        c.frame.tree.setHeadline(u.p,u.oldHead)

        if u.groupCount == 0 and u.oldSel:
            u.c.frame.body.setSelectionRange(u.oldSel)

        u.updateMarks('old')

        for v in u.dirtyVnodeList:
            v.t.setDirty() # Bug fix: Leo 4.4.6.
    #@-node:ekr.20050318085713.1:undoNodeContents
    #@+node:ekr.20080425060424.14:undoPromote
    def undoPromote (self):

        u = self ; c = u.c
        parent_v = u.p._parentVnode()

        # Remove the promoted nodes from parent_v's children.
        n = u.p.childIndex() + 1
        z = parent_v.t.children
        parent_v.t.children = z[:n]
        parent_v.t.children.extend(z[n+len(u.children):])

        # Add the demoted nodes to v's children.
        u.p.t.children = u.children[:]

        # Adjust the parent links of all moved nodes.
        u.p.v._computeParentsOfChildren(children=u.children)

        c.setCurrentPosition(u.p)
    #@-node:ekr.20080425060424.14:undoPromote
    #@+node:ekr.20031218072017.1493:undoRedoText
    def undoRedoText (self,p,
        leading,trailing, # Number of matching leading & trailing lines.
        oldMidLines,newMidLines, # Lists of unmatched lines.
        oldNewlines,newNewlines, # Number of trailing newlines.
        tag="undo", # "undo" or "redo"
        undoType=None):

        # __pychecker__ = '--no-argsused' # newNewlines is unused, but it has symmetry.

        '''Handle text undo and redo: converts _new_ text into _old_ text.'''

        u = self ; c = u.c ; w = c.frame.body.bodyCtrl

        #@    << Compute the result using p's body text >>
        #@+node:ekr.20061106105812.1:<< Compute the result using p's body text >>
        # Recreate the text using the present body text.
        body = p.bodyString()
        body = g.toUnicode(body,"utf-8")
        body_lines = body.split('\n')
        s = []
        if leading > 0:
            s.extend(body_lines[:leading])
        if len(oldMidLines) > 0:
            s.extend(oldMidLines)
        if trailing > 0:
            s.extend(body_lines[-trailing:])
        s = string.join(s,'\n')
        # Remove trailing newlines in s.
        while len(s) > 0 and s[-1] == '\n':
            s = s[:-1]
        # Add oldNewlines newlines.
        if oldNewlines > 0:
            s = s + '\n' * oldNewlines
        result = s

        if u.debug_print:
            print "body:  ",body
            print "result:",result
        #@-node:ekr.20061106105812.1:<< Compute the result using p's body text >>
        #@nl
        p.setBodyString(result)
        w.setAllText(result)
        c.frame.body.recolor(p,incremental=False)
    #@-node:ekr.20031218072017.1493:undoRedoText
    #@+node:ekr.20050408100042:undoRedoTree
    def undoRedoTree (self,p,new_data,old_data):

        '''Replace p and its subtree using old_data during undo.'''

        # Same as undoReplace except uses g.Bunch.

        u = self ; c = u.c

        if new_data == None:
            # This is the first time we have undone the operation.
            # Put the new data in the bead.
            bunch = u.beads[u.bead]
            bunch.newTree = u.saveTree(p.copy())
            u.beads[u.bead] = bunch

        # Replace data in tree with old data.
        u.restoreTree(old_data)
        c.setBodyString(p,p.bodyString())

        return p # Nothing really changes.
    #@-node:ekr.20050408100042:undoRedoTree
    #@+node:ekr.20080425060424.5:undoSort
    def undoSort (self):

        u = self ; c = u.c

        parent_v = u.p._parentVnode()
        parent_v.t.children = u.oldChildren
        c.setPositionAfterSort(u.sortChildren)

    #@-node:ekr.20080425060424.5:undoSort
    #@+node:ekr.20050318085713.2:undoTree
    def undoTree (self):

        '''Redo replacement of an entire tree.'''

        u = self ; c = u.c

        u.p = self.undoRedoTree(u.p,u.newTree,u.oldTree)
        c.selectPosition(u.p) # Does full recolor.
        if u.oldSel:
            c.frame.body.setSelectionRange(u.oldSel)
    #@-node:ekr.20050318085713.2:undoTree
    #@+node:EKR.20040526090701.4:undoTyping
    def undoTyping (self):

        u = self ; c = u.c ; current = c.currentPosition()
        w = c.frame.body.bodyCtrl

        # selectPosition causes recoloring, so don't do this unless needed.
        if current != u.p:
            c.selectPosition(u.p)
        elif u.undoType in ("Cut","Paste",'Clear Recent Files'):
            c.frame.body.forceFullRecolor()

        self.undoRedoText(
            u.p,u.leading,u.trailing,
            u.oldMiddleLines,u.newMiddleLines,
            u.oldNewlines,u.newNewlines,
            tag="undo",undoType=u.undoType)

        u.updateMarks('old')

        for v in u.dirtyVnodeList:
            v.t.setDirty() # Bug fix: Leo 4.4.6.

        if u.oldSel:
            c.bodyWantsFocusNow()
            i,j = u.oldSel
            w.setSelectionRange(i,j,insert=j)
        if u.yview:
            c.bodyWantsFocusNow()
            c.frame.body.setYScrollPosition(u.yview)
    #@-node:EKR.20040526090701.4:undoTyping
    #@-node:ekr.20031218072017.2039:undo & helpers...
    #@-others
#@-node:ekr.20031218072017.3605:class undoer
#@+node:ekr.20031218072017.2243:class nullUndoer (undoer)
class nullUndoer (undoer):

    def __init__ (self,c):

        undoer.__init__(self,c) # init the base class.

    #@    @+others
    #@+node:ekr.20050415165731:other methods
    def clearUndoState (self):
        pass

    def canRedo (self):
        return False

    def canUndo (self):
        return False

    def enableMenuItems (self):
        pass

    def setUndoTypingParams (self,p,undo_type,oldText,newText,oldSel,newSel,oldYview=None):
        pass

    def setUndoTypes (self):
        pass
    #@-node:ekr.20050415165731:other methods
    #@+node:ekr.20050415165731.1:before undo handlers...
    def beforeChangeNodeContents (self,p,oldBody=None,oldHead=None):
        pass
    def beforeChangeTree (self,p):
        pass
    def beforeChangeGroup (self,p,command):
        pass
    def beforeClearRecentFiles (self):
        pass
    def beforeCloneNode (self,p):
        pass
    def beforeDeleteNode (self,p):
        pass
    def beforeInsertNode (self,p,pasteAsClone=False,copiedBunchList=[]):
        pass
    def beforeMark (self,p,command):
        pass
    def beforeMoveNode (self,p):
        pass
    #@-node:ekr.20050415165731.1:before undo handlers...
    #@+node:ekr.20050415170018:after undo handlers...
    def afterChangeNodeContents (self,p,command,bunch,dirtyVnodeList=[]):
        pass
    def afterChangeTree (self,p,command,bunch):
        pass
    def afterChangeGroup (self,p,command,reportFlag=False,dirtyVnodeList=[]):
        pass
    def afterClearRecentFiles (self,bunch):
        pass
    def afterCloneNode (self,p,command,bunch,dirtyVnodeList=[]):
        pass
    def afterDehoist (self,p,command):
        pass
    def afterHoist (self,p,command):
        pass
    def afterDeleteNode (self,p,command,bunch,dirtyVnodeList=[]):
        pass
    def afterInsertNode (self,p,command,bunch,dirtyVnodeList=[]):
        pass

    def afterMark (self,p,command,bunch,dirtyVnodeList=[]):
        pass

    def afterMoveNode (self,p,command,bunch,dirtyVnodeList=[]):
        pass
    #@-node:ekr.20050415170018:after undo handlers...
    #@-others
#@-node:ekr.20031218072017.2243:class nullUndoer (undoer)
#@-others
#@-node:ekr.20031218072017.3603:@thin leoUndo.py
#@-leo
