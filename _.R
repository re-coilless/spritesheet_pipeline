# https://docs.google.com/document/d/1kbAj0zoD8Q9MXuCsqIKCf_G6E4mpA7y8s13creelBUY/edit?tab=t.0

library(luajr)
library(magick)

`%||%` <- function(a,b) if(is.null(a)) b else a
painter <- function(p,x,y,r,g,b,a){
  p[1,x,y] <- as.raw(r)
  p[2,x,y] <- as.raw(g)
  p[3,x,y] <- as.raw(b)
  p[4,x,y] <- as.raw(a)
  return(p)
}
zoomer <- function(p,x,y,w,h){
  map <- data.frame(x=99999,y=99999,w=-1,h=-1)
  for(i in 1:w){
    for(e in 1:h){
      if(p[4,x+i,y+e]!=0){
        map$x <- min(map$x,x+i)
        map$y <- min(map$y,y+e)
        map$w <- max(map$w,x+i)
        map$h <- max(map$h,y+e)
      }
    }
  }
  return(map)
}

path <- "_/player.xml"
xml = lua_func("function(file) return dofile(\"_/_nxml.lua\").parse(file) end")
anim_data <- xml(readChar(path,file.info(path)$size))
print(anim_data$attr)
pic <- image_read("_/player.png")
pic_data <- image_data(pic,channels="rgba")
print(pic)
#src <- image_read("_/player_uv_src.png")
#src_data <- image_data(src,channels="rgba")
#print(src)

step <- 0
mapping <- data.frame()
got_default <- FALSE
pos_x <- pos_y <- width <- height <- 0
for(anim in anim_data$children){
  if(anim$name!="RectAnimation"){ next }
  if(!is.null(anim$attr$parent)){ next }
  
  is_default <- anim$attr$name==anim_data$attr$default_animation
  if(!is_default && !got_default){
    next
  }else if(is_default){
    got_default <- TRUE
    pos_x <- anim$attr$pos_x
    pos_y <- as.numeric(anim$attr$pos_y)
    width <- anim$attr$frame_width
    height <- anim$attr$frame_height
  }else{
    if(step==0){ step <- as.numeric(anim$attr$pos_y)-pos_y }
    pos_y <- pos_y+step
  }
  
  frame_x <- as.numeric(anim$attr$pos_x %||% pos_x)
  frame_y <- as.numeric(anim$attr$pos_y %||% pos_y)
  frame_w <- as.numeric(anim$attr$frame_width %||% width)
  frame_h <- as.numeric(anim$attr$frame_height %||% height)
  anim_length <- as.numeric(anim$attr$frame_count)
  cat(anim$attr$name,frame_x,frame_y,frame_w,frame_h,anim_length,"\n")

  for(i in 0:(anim_length-1)){
    map <- zoomer(pic_data,frame_x+i*frame_w,frame_y,frame_w,frame_h)
    mapping <- rbind(mapping,map)
  }
}

#size of the map should be based on the max single-frame size
#if no src detected, just do simple mode
#cut out white stuff
#rgb value shifts should be based on proximity to src anchors
#allow arbitrary anchor color, just track them
for(k in seq_len(nrow(mapping))){
  map <- mapping[k,]
  step_x <- 255/(map$w-map$x)
  step_y <- 255/(map$h-map$y)
  for(i in map$x:map$w){
    for(e in map$y:map$h){
      if(pic_data[4,i,e]==0){ next }
      pic_data <- painter(pic_data,i,e,step_x*(i-map$x),step_y*(e-map$y),0,255)
    }
  }
}

#https://colab.research.google.com/drive/1s1b7Kr97Q5aUpzJrom12YszZQyWGRgsi
print("[DONE]")
image_write(image_read(pic_data),path="_/stains.png",format="png")